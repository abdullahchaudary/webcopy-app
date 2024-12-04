import os
import re
import tkinter as tk
from tkinter import messagebox
from urllib.parse import urlparse, urljoin
import requests
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor
import threading
import time

class WebsiteDownloader:
    def __init__(self, root):
        self.root = root
        self.root.title("Website Downloader")
        self.root.geometry("600x400")

        self.url_label = tk.Label(root, text="Enter URL:")
        self.url_label.pack()
        self.url_entry = tk.Entry(root, width=50)
        self.url_entry.pack()

        self.button_frame = tk.Frame(root)
        self.button_frame.pack(pady=10)

        self.download_button = tk.Button(self.button_frame, text="Download", command=self.start_download)
        self.download_button.pack(side=tk.LEFT)

        self.reset_button = tk.Button(self.button_frame, text="Reset", command=self.reset, state=tk.DISABLED)
        self.reset_button.pack(side=tk.LEFT)

        self.console_output = tk.Text(root, height=15, width=70, state=tk.DISABLED)
        self.console_output.pack()

        self.executor = ThreadPoolExecutor(max_workers=10)
        self.visited_urls = set()
        self.lock = threading.Lock()
        self.total_files = 0
        self.downloaded_files = 0
        self.retry_attempts = 3
        self.is_downloading = False

    def log_message(self, message):
        self.console_output.configure(state=tk.NORMAL)
        self.console_output.insert(tk.END, message + "\n")
        self.console_output.see(tk.END)
        self.console_output.configure(state=tk.DISABLED)

    def start_download(self):
        url = self.url_entry.get()
        if not url.startswith("http"):
            messagebox.showerror("Error", "Please enter a valid URL starting with http or https.")
            return

        folder_name = urlparse(url).netloc
        os.makedirs(folder_name, exist_ok=True)

        self.visited_urls.clear()
        self.downloaded_files = 0
        self.total_files = 0

        self.log_message(f"Starting download for: {url}")
        self.download_button.config(text="Cancel", command=self.cancel_download)
        self.reset_button.config(state=tk.DISABLED)
        self.is_downloading = True

        self.executor.submit(self.download_page, url, folder_name, "index.html")

    def reset(self):
        self.url_entry.delete(0, tk.END)
        self.console_output.configure(state=tk.NORMAL)
        self.console_output.delete(1.0, tk.END)
        self.console_output.configure(state=tk.DISABLED)
        self.download_button.config(text="Download", command=self.start_download)
        self.reset_button.config(state=tk.DISABLED)
        self.is_downloading = False

    def cancel_download(self):
        self.executor.shutdown(wait=False)
        self.log_message("Download canceled.")
        self.download_button.config(text="Download", command=self.start_download)
        self.reset_button.config(state=tk.NORMAL)
        self.is_downloading = False

    def download_page(self, url, folder_name, relative_path, retries=0):
        with self.lock:
            if url in self.visited_urls:
                return
            self.visited_urls.add(url)

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            file_path = os.path.join(folder_name, relative_path)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            with open(file_path, "wb") as file:
                file.write(response.content)
            self.downloaded_files += 1
            self.log_message(f"Downloaded: {url}")

            self.parse_html(response.text, url, folder_name)

            self.check_download_completion()

        except requests.RequestException as e:
            self.log_message(f"Error downloading {url}: {e}")
            if retries < self.retry_attempts:
                time.sleep(2)
                self.download_page(url, folder_name, relative_path, retries + 1)

    def parse_html(self, html_content, base_url, folder_name):
        soup = BeautifulSoup(html_content, "html.parser")

        for tag in soup.find_all(["img", "link", "script", "a"]):
            asset_url = None
            if tag.name == "img" and tag.get("src"):
                asset_url = urljoin(base_url, tag["src"])
            elif tag.name == "link" and tag.get("href") and tag["rel"] in [["stylesheet"], ["icon"]]:
                asset_url = urljoin(base_url, tag["href"])
            elif tag.name == "script" and tag.get("src"):
                asset_url = urljoin(base_url, tag["src"])
            elif tag.name == "a" and tag.get("href"):
                href = tag["href"]
                if not href.startswith('#') and self.is_internal_link(href, base_url):
                    asset_url = urljoin(base_url, href)

            if asset_url:
                if tag.name == "a":
                    self.queue_internal_page(asset_url, folder_name)
                else:
                    self.queue_asset(asset_url, folder_name)

        for tag in soup.find_all(style=True):
            style = tag["style"]
            bg_image_pattern = re.compile(r'url\(["\']?(.*?)["\']?\)')
            for match in bg_image_pattern.finditer(style):
                asset_url = urljoin(base_url, match.group(1))
                if self.is_internal_link(asset_url, base_url):
                    self.queue_asset(asset_url, folder_name)
                    self.log_message(f"Queued asset from style: {asset_url}")

        if not any(bg_image_pattern.finditer(tag["style"]) for tag in soup.find_all(style=True)):
            self.log_message("No background images found in style attributes.")


    def queue_internal_page(self, url, folder_name):
        with self.lock:
            if url not in self.visited_urls:
                relative_path = self.get_relative_path(url)
                self.total_files += 1
                # self.total_files = len(self.visited_urls)
                self.executor.submit(self.download_page, url, folder_name, relative_path)

    def queue_asset(self, url, folder_name):
        with self.lock:
            if url not in self.visited_urls:
                relative_path = self.get_relative_path(url)
                self.total_files += 1
                # self.total_files = len(self.visited_urls)
                self.executor.submit(self.download_asset, url, folder_name, relative_path)

    def download_asset(self, url, folder_name, relative_path, retries=0):
        with self.lock:
            if url in self.visited_urls:
                return
            self.visited_urls.add(url)

        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            file_path = os.path.join(folder_name, relative_path)
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            with open(file_path, "wb") as file:
                file.write(response.content)
            self.downloaded_files += 1
            self.log_message(f"Downloaded asset: {url}")

            content_type = response.headers.get("Content-Type", "")
            if "text/css" in content_type:
                self.parse_css_for_assets(response.text, url, folder_name)
            elif "javascript" in content_type:
                self.parse_js_for_assets(response.text, url, folder_name)

            self.check_download_completion()

        except requests.RequestException as e:
            self.log_message(f"Error downloading asset {url}: {e}")
            if retries < self.retry_attempts:
                time.sleep(2)
                self.download_asset(url, folder_name, relative_path, retries + 1)

    def check_download_completion(self):
        with self.lock:
            print(f"Downloaded: {self.downloaded_files}, Total: {self.total_files}, Is downloading: {self.is_downloading}")
            if self.downloaded_files >= self.total_files and self.is_downloading:
                self.log_message("Download completed!")
                messagebox.showinfo("Download Complete", "All files downloaded successfully.")
                self.download_button.config(text="Download", command=self.start_download)
                self.reset_button.config(state=tk.NORMAL)
                self.is_downloading = False

    def parse_css_for_assets(self, css_content, base_url, folder_name):
        css_url_pattern = re.compile(r'url\(["\']?(.*?)["\']?\)')
        for match in css_url_pattern.finditer(css_content):
            asset_url = urljoin(base_url, match.group(1))
            if self.is_internal_link(asset_url, base_url):
                self.queue_asset(asset_url, folder_name)

    def parse_js_for_assets(self, js_content, base_url, folder_name):
        js_url_pattern = re.compile(r'(["\'])(https?://.*?)(["\'])')
        for match in js_url_pattern.finditer(js_content):
            asset_url = match.group(2)
            if self.is_internal_link(asset_url, base_url):
                self.queue_asset(asset_url, folder_name)

    def is_internal_link(self, link, base_url):
        parsed_link = urlparse(urljoin(base_url, link))
        parsed_base = urlparse(base_url)
        return parsed_link.netloc == parsed_base.netloc

    def get_relative_path(self, url):
        parsed_url = urlparse(url)
        relative_path = parsed_url.path.lstrip('/')
        return relative_path if relative_path else 'index.html'

if __name__ == "__main__":
    root = tk.Tk()
    app = WebsiteDownloader(root)
    root.mainloop()
