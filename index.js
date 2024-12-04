const logOutput = document.getElementById("logOutput");

function logMessage(message) {
    const logLine = document.createElement("div");
    logLine.textContent = message;
    logOutput.appendChild(logLine);
    logOutput.scrollTop = logOutput.scrollHeight;
}

async function startDownload() {
    const url = document.getElementById("urlInput").value.trim();
    if (!url) {
        logMessage("Please enter a valid URL.");
        return;
    }

    logMessage(`Starting download for: ${url}`);

    try {
        const rootDirectory = await window.showDirectoryPicker();
        const siteFolder = await createSiteFolder(rootDirectory, url);
        const visitedUrls = new Set();
        const downloadedAssets = new Set();
        await downloadPage(url, siteFolder, visitedUrls, downloadedAssets);
        logMessage("Download complete!");
    } catch (err) {
        logMessage(`Error: ${err.message}`);
        console.log(err)
    }
}

async function createSiteFolder(rootDirectory, url) {
    const { host } = new URL(url);
    return await rootDirectory.getDirectoryHandle(host, { create: true });
}

async function downloadPage(url, directoryHandle, visitedUrls, downloadedAssets) {
    if (visitedUrls.has(url)) return;
    visitedUrls.add(url);

    const response = await fetch(url);
    if (!response.ok) throw new Error(`Failed to download ${url}: ${response.statusText}`);

    const htmlContent = await response.text();
    const pageFileName = getFileNameFromUrl(url, "html");
    const pagePath = getPathFromUrl(url);

    await saveFile(pagePath, pageFileName, htmlContent, directoryHandle);
    logMessage(`Downloaded page: ${url}`);

    const assets = new Set();
    const internalLinks = new Set();
    parseHtml(htmlContent, url, assets, internalLinks);

    for (const link of internalLinks) {
        await downloadPage(link, directoryHandle, visitedUrls, downloadedAssets);
    }

    for (const assetUrl of assets) {
        await downloadAsset(assetUrl, directoryHandle, downloadedAssets);
    }
}

function parseHtml(htmlContent, baseUrl, assets, internalLinks) {
    const doc = new DOMParser().parseFromString(htmlContent, "text/html");

    doc.querySelectorAll("img[src], link[href], script[src]").forEach(tag => {
        const url = tag.getAttribute("src") || tag.getAttribute("href");
        if (url) {
            const fullUrl = new URL(url, baseUrl).href;
            if (isSameDomain(fullUrl, baseUrl)) assets.add(fullUrl);
        }
    });

    doc.querySelectorAll("a[href]").forEach(tag => {
        const href = tag.getAttribute("href");
        if (href && !href.startsWith("#")) {
            const fullUrl = new URL(href, baseUrl).href;
            if (isSameDomain(fullUrl, baseUrl)) internalLinks.add(fullUrl);
        }
    });

    extractAssetsFromCss(doc, baseUrl, assets);
}

function extractAssetsFromCss(doc, baseUrl, assets) {
    doc.querySelectorAll("[style]").forEach(tag => {
        const style = tag.getAttribute("style");
        extractUrlsFromCss(style, baseUrl, baseUrl).forEach(url => assets.add(url));
    });

    doc.querySelectorAll("link[rel='stylesheet']").forEach(cssLink => {
        const cssUrl = cssLink.getAttribute("href");
        const fullCssUrl = new URL(cssUrl, baseUrl).href;
        if (isSameDomain(fullCssUrl, baseUrl)) {
            assets.add(fullCssUrl);
            fetchCssAndExtractAssets(fullCssUrl, baseUrl, assets);
        }
    });
}

async function fetchCssAndExtractAssets(cssUrl, baseUrl, assets) {
    const response = await fetch(cssUrl);
    const cssContent = await response.text();
    extractUrlsFromCss(cssContent, baseUrl, cssUrl).forEach(url => assets.add(url));
}

function extractUrlsFromCss(cssText, baseUrl, cssUrl) {
    const urlRegex = /url\(["']?(.*?)["']?\)/g;
    const urls = new Set();
    
    const baseUrlObj = new URL(baseUrl);
    const cssUrlObj = new URL(cssUrl);
    
    let match;
    while ((match = urlRegex.exec(cssText)) !== null) {
        let url = match[1].trim().replace(/["']/g, '');
        
        if (url.startsWith('data:')) continue;
        
        if (url.startsWith('http') && !isSameDomain(url, baseUrl)) continue;
        
        url = url.split('?')[0];
        
        if (!url.startsWith('http')) {
            const assetPath = cssUrlObj.pathname;
            const assetDir = assetPath.substring(0, assetPath.lastIndexOf('/'));
            
            let finalPath;
            if (url.startsWith('/')) {
                finalPath = url;
            } else if (url.startsWith('../')) {
                let tempDir = assetDir;
                while (url.startsWith('../')) {
                    tempDir = tempDir.substring(0, tempDir.lastIndexOf('/'));
                    url = url.substring(3);
                }
                finalPath = `${tempDir}/${url}`;
            } else if (url.startsWith('./')) {
                finalPath = `${assetDir}/${url.substring(2)}`;
            } else {
                finalPath = `${assetDir}/${url}`;
            }
            
            url = baseUrlObj.origin + finalPath;
        }
        
        if (isSameDomain(url, baseUrl)) {
            urls.add(url);
        }
    }
    
    return Array.from(urls);
}

async function downloadAsset(assetUrl, directoryHandle, downloadedAssets) {
    if (downloadedAssets.has(assetUrl)) return;
    downloadedAssets.add(assetUrl);

    const response = await fetch(assetUrl);
    if (!response.ok) {
        logMessage(`Failed to download asset ${assetUrl}: ${response.statusText}`);
        return;
    }

    const blob = await response.blob();
    const assetFilePath = getPathFromUrl(assetUrl);
    const assetFileName = getFileNameFromUrl(assetUrl);
    await saveFile(assetFilePath, assetFileName, blob, directoryHandle);
    logMessage(`Downloaded asset: ${assetUrl}`);
}

function isSameDomain(url, baseUrl) {
    return new URL(url).host === new URL(baseUrl).host;
}

async function saveFile(filePath, fileName, content, baseDir) {
    const pathParts = filePath.split('/');
    
    let currentDir = baseDir;

    for (let i = 0; i < pathParts.length - 1; i++) {
        const dirName = pathParts[i];
        currentDir = await createDirectory(currentDir, dirName);
    }

    const fileHandle = await currentDir.getFileHandle(fileName, { create: true });
    const writable = await fileHandle.createWritable();
    await writable.write(content);
    await writable.close();
}

async function createDirectory(currentDir, dirName) {
    try {
        return await currentDir.getDirectoryHandle(dirName, { create: true });
    } catch (e) {
        console.error('Error creating directory:', e);
        return currentDir;
    }
}

function getPathFromUrl(url) {
    const parsedUrl = new URL(url);
    return parsedUrl.pathname.replace(/^\/+/, "").replace(/[\/:*?"<>|]/g, "/");
}

function getFileNameFromUrl(url, extension = "") {
    const path = getPathFromUrl(url);
    const lastSlashIndex = path.lastIndexOf("/");
    let fileName = path.substring(lastSlashIndex + 1) || "index";
    if (extension && !fileName.endsWith(`.${extension}`)) {
        fileName += `.${extension}`;
    }
    return fileName;
}

document.getElementById("downloadBtn").addEventListener("click", startDownload);