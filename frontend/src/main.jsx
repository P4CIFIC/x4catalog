import { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';

const get = async (path, options = {}) => {
  const response = await fetch(path, {
    headers: { 'content-type': 'application/json' },
    ...options,
  });
  if (!response.ok) throw new Error((await response.text()) || `Request failed: ${response.status}`);
  return response.json();
};

const prettyTag = (name) => name.replaceAll('-', ' ').replaceAll('_', ' ');
const SLEEP_SCREEN_DIRECTORY = '/.sleep';
const DEFAULT_CROSSPOINT_DESTINATION = SLEEP_SCREEN_DIRECTORY;
const DEFAULT_BOOK_DIRECTORY = '/';
const BOOK_EXTENSIONS = Object.freeze(['.epub', '.xtc', '.xtch', '.txt']);
const DEFAULT_CROSSPOINT_HOST = 'crosspoint.local';
const PAGE_PATH = window.location.pathname.replace(/\/+$/, '') || '/';
const PUBLIC_DEMO = import.meta.env.VITE_PUBLIC_DEMO === '1';
const HOSTED = import.meta.env.VITE_HOSTED === '1';
const PAGE = PAGE_PATH === '/device' ? 'device'
  : PAGE_PATH === '/docs' ? 'docs'
  : PAGE_PATH === '/browse' ? 'browse'
  : (HOSTED ? 'home' : 'browse');
const DEVICE_PAGE = PAGE === 'device';
const LIVE_DEVICE = !PUBLIC_DEMO && (HOSTED || window.location.protocol === 'http:');
const READ_ONLY_ARCHIVE = PUBLIC_DEMO || HOSTED;
const SHOW_CLUSTERS = !HOSTED && !PUBLIC_DEMO;
const HTTPS_PAGE = window.location.protocol === 'https:';
const supportsTargetAddressSpace = () => {
  try {
    return typeof Request !== 'undefined' && 'targetAddressSpace' in Request.prototype;
  } catch (_) {
    return false;
  }
};
const IMAGE_PAGE_SIZE = 160;
const GITHUB_URL = 'https://github.com/P4CIFIC/x4catalog';
const CROSSPOINT_GUIDE_URL = 'https://crosspoint-cloud.idlerecord.com/en';
const CROSSPOINT_REPO_URL = 'https://github.com/crosspoint-reader/crosspoint-reader';
const GitHubMark = () => <svg viewBox="0 0 16 16" width="18" height="18" aria-hidden="true"><path fill="currentColor" d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" /></svg>;
const isFinePointer = (event) => event.pointerType === 'mouse' || event.pointerType === 'pen' || !event.pointerType;
const SENSITIVE_TAGS = new Set(['nsfw', 'nudity', 'partial-nudity', 'explicit-nudity', 'suggestive', 'sexualized', 'fetish', 'violence', 'gore', 'graphic-violence']);
const itemIsSensitive = (item) => item.sensitive === true || (item.tags || []).some((tag) => SENSITIVE_TAGS.has(String(tag.name || '').toLowerCase()));
const savedShowSensitive = () => localStorage.getItem('x4-show-sensitive') === '1';

const DEMO_IMAGES = Object.freeze([
  { id: 1, filename: 'moonlit-archive_x4.bmp', decision: 'unreviewed', mean_luma: 34, edge_density: .12, x4_suitability: 'excellent', ocr_processed: true, ocr_text: '', tags: [{ name: 'moon', source: 'machine', confidence: .94 }, { name: 'night', source: 'machine', confidence: .91 }, { name: 'high-contrast', source: 'machine', confidence: .88 }], label_evidence: [], demo: true, tone: 'moon', mark: '01' },
  { id: 2, filename: 'forest-study_x4.bmp', decision: 'unreviewed', mean_luma: 58, edge_density: .24, x4_suitability: 'good', ocr_processed: true, ocr_text: '', tags: [{ name: 'forest', source: 'machine', confidence: .89 }, { name: 'nature', source: 'machine', confidence: .86 }, { name: 'tree', source: 'machine', confidence: .84 }], label_evidence: [], demo: true, tone: 'forest', mark: '02' },
  { id: 3, filename: 'reading-notes_x4.bmp', decision: 'unreviewed', mean_luma: 82, edge_density: .18, x4_suitability: 'small-text', ocr_processed: true, ocr_text: 'A short note about the next chapter.', tags: [{ name: 'english-text', source: 'machine', confidence: .96 }, { name: 'text-focus', source: 'machine', confidence: .90 }], label_evidence: [], demo: true, tone: 'paper', mark: '03' },
  { id: 4, filename: 'character-study_x4.bmp', decision: 'unreviewed', mean_luma: 67, edge_density: .31, x4_suitability: 'acceptable', ocr_processed: true, ocr_text: '', tags: [{ name: 'illustration', source: 'machine', confidence: .92 }, { name: 'character', source: 'machine', confidence: .87 }, { name: 'bold', source: 'machine', confidence: .85 }], label_evidence: [], demo: true, tone: 'figure', mark: '04' },
  { id: 5, filename: 'coastline-study_x4.bmp', decision: 'unreviewed', mean_luma: 73, edge_density: .16, x4_suitability: 'good', ocr_processed: true, ocr_text: '', tags: [{ name: 'sea', source: 'machine', confidence: .90 }, { name: 'landscape', source: 'machine', confidence: .88 }, { name: 'horizon', source: 'machine', confidence: .82 }], label_evidence: [], demo: true, tone: 'coast', mark: '05' },
  { id: 6, filename: 'bold-shape_x4.bmp', decision: 'unreviewed', mean_luma: 48, edge_density: .39, x4_suitability: 'excellent', ocr_processed: true, ocr_text: '', tags: [{ name: 'abstract', source: 'machine', confidence: .93 }, { name: 'high-contrast', source: 'machine', confidence: .90 }, { name: 'pattern', source: 'machine', confidence: .86 }], label_evidence: [], demo: true, tone: 'shape', mark: '06' },
]);
const DEMO_TAGS = Object.freeze([
  { name: 'moon', category: 'subject', automatic_count: 184 },
  { name: 'forest', category: 'subject', automatic_count: 142 },
  { name: 'english-text', category: 'content', automatic_count: 96 },
  { name: 'illustration', category: 'style', automatic_count: 88 },
  { name: 'high-contrast', category: 'intensity', automatic_count: 74 },
  { name: 'bold', category: 'intensity', automatic_count: 53 },
]);
const DEMO_CLUSTERS = Object.freeze([
  { id: 1, image_count: 24, outlier_count: 2 },
  { id: 2, image_count: 18, outlier_count: 1 },
  { id: 3, image_count: 11, outlier_count: 0 },
]);
const DEMO_STATUS = Object.freeze({ version: '1.5.0', device: 'X4', serial: 'PUBLIC-PREVIEW', freeBytes: 2147483648, totalBytes: 4294967296 });
const DEMO_SLEEP_FILES = Object.freeze([{ name: 'winter-window.bmp', size: 480000, path: '/.sleep/winter-window.bmp', url: null, demo: true }]);
const DEMO_BOOK_LISTINGS = Object.freeze({
  '/': {
    folders: [{ name: 'Reading', path: '/Reading' }, { name: 'Reference', path: '/Reference' }],
    books: [
      { name: 'The Dispossessed.epub', size: 1840000, path: '/The Dispossessed.epub', directory: '/', url: null, demo: true },
      { name: 'A Wizard of Earthsea.xtc', size: 920000, path: '/A Wizard of Earthsea.xtc', directory: '/', url: null, demo: true },
    ],
  },
  '/Reading': {
    folders: [],
    books: [{ name: 'The Left Hand of Darkness.epub', size: 2310000, path: '/Reading/The Left Hand of Darkness.epub', directory: '/Reading', url: null, demo: true }],
  },
  '/Reference': {
    folders: [],
    books: [{ name: 'Field Notes.txt', size: 84000, path: '/Reference/Field Notes.txt', directory: '/Reference', url: null, demo: true }],
  },
});

const savedCrossPointHost = () => {
  const stored = localStorage.getItem('x4-crosspoint-host');
  if (!stored) return DEFAULT_CROSSPOINT_HOST;
  return normalizeCrossPointHost(stored) || DEFAULT_CROSSPOINT_HOST;
};

const normalizeCrossPointHost = (host) => String(host || '')
  .trim()
  .replace(/^wss?:\/\//, '')
  .replace(/^https?:\/\//, '')
  .replace(/\/+$/, '')
  .replace(/:0$/, '');

const crossPointSocketUrl = (host) => {
  const value = normalizeCrossPointHost(host);
  if (!value) throw new Error('Enter the CrossPoint host or IP address.');
  return `ws://${value.includes(':') ? value : `${value}:81`}/`;
};

const crossPointHostValue = (host) => {
  const value = normalizeCrossPointHost(host);
  if (!value || /[\/\\?#\s]/.test(value)) throw new Error('Enter a CrossPoint IP address or hostname.');
  return value;
};

const crossPointDeviceUrl = (host, path) => `http://${crossPointHostValue(host)}${path}`;

const readCrossPointResponse = async (response) => {
  const body = await response.text();
  if (!response.ok) {
    let message = body;
    try { message = JSON.parse(body).detail || body; } catch (_) { /* plain text response */ }
    throw new Error(message || `CrossPoint request failed: ${response.status}`);
  }
  if (!body) return null;
  const contentType = response.headers.get('content-type') || '';
  if (contentType.includes('application/json')) return JSON.parse(body);
  return body;
};

const localNetworkAddressSpace = (host) => {
  try {
    const hostname = crossPointHostValue(host).split(':')[0].toLowerCase();
    if (hostname === '127.0.0.1' || hostname === 'localhost' || hostname === '[::1]' || hostname === '::1') return 'loopback';
    return 'local';
  } catch (_) {
    return 'local';
  }
};

const localNetworkFetchOptions = (host) => {
  if (!HTTPS_PAGE || !supportsTargetAddressSpace()) return {};
  return { targetAddressSpace: localNetworkAddressSpace(host) };
};

const localNetworkError = (host, error) => {
  if (HTTPS_PAGE && !supportsTargetAddressSpace()) {
    return new Error(`This browser cannot talk to the X4 from this website. Try Chrome, or see How to.`);
  }
  const transient = error?.name === 'AbortError' || String(error?.message || '').includes('Failed to fetch');
  if (HTTPS_PAGE && transient) {
    return new Error(`Could not reach the X4 at ${host}. Same Wi-Fi? Click Allow if asked. Try the numbers from the X4 screen. See How to.`);
  }
  if (error instanceof Error && error.message && !transient) return error;
  return new Error(`Could not reach the X4 at ${host}.`);
};

const fetchWithTimeout = async (url, options = {}, timeoutMs = 5000) => {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    window.clearTimeout(timer);
  }
};

const crossPointRequest = async (host, path, options = {}) => {
  const [rawPath, rawQuery = ''] = path.split('?');
  const localPath = rawPath.startsWith('/api/') ? rawPath.slice(4) : rawPath;
  const directParams = new URLSearchParams(rawQuery);
  const proxyParams = new URLSearchParams(rawQuery);
  const normalizedHost = crossPointHostValue(host);
  proxyParams.set('host', normalizedHost);
  const requestOptions = { ...options, headers: { Accept: 'application/json, text/plain, image/*', ...(options.headers || {}) } };

  // CrossPoint 1.5 enables CORS. Use it directly so the browser can talk to
  // the device without routing image/file traffic through the catalog server.
  // Translate our JSON action payloads to the device's form-encoded API.
  const directOptions = { ...requestOptions };
  if (directOptions.body && String(directOptions.headers['content-type'] || '').includes('application/json')) {
    try {
      const payload = JSON.parse(directOptions.body);
      delete payload.host;
      directOptions.body = new URLSearchParams(Object.entries(payload).map(([key, value]) => [key, String(value)])).toString();
      directOptions.headers = { ...directOptions.headers, 'content-type': 'application/x-www-form-urlencoded' };
    } catch (_) {
      // Let the proxy handle malformed action payloads and return its normal error.
    }
  }
  const networkOptions = localNetworkFetchOptions(normalizedHost);
  try {
    return await readCrossPointResponse(await fetchWithTimeout(`${crossPointDeviceUrl(normalizedHost, rawPath)}${directParams.toString() ? `?${directParams.toString()}` : ''}`, { ...directOptions, ...networkOptions }));
  } catch (directError) {
    // Hosted HTTPS has no FastAPI proxy. A pre-1.5 device on localhost still
    // falls back through the loopback catalog.
    if (!HOSTED) {
      try {
        return await readCrossPointResponse(await fetchWithTimeout(`/api/crosspoint${localPath}?${proxyParams.toString()}`, requestOptions));
      } catch (_) {
        throw localNetworkError(normalizedHost, directError);
      }
    }
    throw localNetworkError(normalizedHost, directError);
  }
};

const bytesLabel = (bytes) => {
  if (!Number.isFinite(bytes)) return 'unknown';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(0)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
};

const numericField = (object, keys) => {
  for (const key of keys) {
    const value = Number(object?.[key]);
    if (Number.isFinite(value) && value >= 0) return value;
  }
  return null;
};

const hostedCdnOrigin = (item) => {
  const hint = String(item?.thumbnail_url || item?.source_url || '');
  for (const marker of ['/thumbs/', '/sources/']) {
    const index = hint.indexOf(marker);
    if (index > 0) return hint.slice(0, index);
  }
  return '';
};

const hostedSourceUrl = (item) => {
  if (item?.source_url) return item.source_url;
  const digest = String(item?.sha256 || '');
  const origin = hostedCdnOrigin(item);
  if (digest && origin) return `${origin}/sources/${digest}.bmp`;
  return '';
};

const sourceUrlForSend = (detail, id) => hostedSourceUrl(detail) || (!HOSTED ? `/api/images/${id}/source` : '');

const blobIsBmp = async (blob) => {
  const header = new Uint8Array(await blob.slice(0, 2).arrayBuffer());
  return header.length === 2 && header[0] === 0x42 && header[1] === 0x4d;
};

const parseDeviceStorage = (status, storagePayload, listedBytes) => {
  const source = storagePayload?.storage || storagePayload || status?.storage || status?.sd || status || {};
  // CrossPoint 1.5 /api/status reports freeHeap (RAM), not SD card capacity.
  const totalBytes = numericField(source, ['totalBytes', 'total_bytes', 'sdTotalBytes', 'capacityBytes', 'capacity']);
  const usedBytes = numericField(source, ['usedBytes', 'used_bytes', 'sdUsedBytes']);
  const freeBytes = numericField(source, ['freeBytes', 'free_bytes', 'availableBytes', 'available', 'sdFreeBytes']);
  const derivedUsed = totalBytes !== null && freeBytes !== null ? Math.max(totalBytes - freeBytes, 0) : null;
  const derivedFree = totalBytes !== null && usedBytes !== null ? Math.max(totalBytes - usedBytes, 0) : null;
  return {
    totalBytes,
    usedBytes: usedBytes ?? derivedUsed,
    freeBytes: freeBytes ?? derivedFree,
    listedBytes,
  };
};

const joinDevicePath = (directory, name) => `${directory === '/' ? '' : directory}/${name}`;
const deviceFileUrl = (host, filePath) => {
  const path = `/download?${new URLSearchParams({ path: filePath }).toString()}`;
  return crossPointDeviceUrl(host, path);
};

const normalizeDeviceDirectory = (value, { fallback = DEFAULT_BOOK_DIRECTORY, allowSleep = false } = {}) => {
  const raw = String(value || fallback).trim() || fallback;
  const withLeadingSlash = raw.startsWith('/') ? raw : `/${raw}`;
  const normalized = withLeadingSlash.replace(/\/+/g, '/');
  const segments = normalized.split('/').filter(Boolean);
  const hiddenSegment = segments.some((segment) => segment === '.' || segment === '..' || segment.startsWith('.'));
  const isSleepDirectory = normalized === SLEEP_SCREEN_DIRECTORY;
  if (hiddenSegment && !(allowSleep && isSleepDirectory)) {
    throw new Error(allowSleep ? 'Choose the X4 sleep screens or a visible custom folder.' : 'Books can only use visible X4 folders.');
  }
  return normalized === '/' ? '/' : normalized.replace(/\/+$/, '') || '/';
};

const normalizeBookDirectory = (value) => normalizeDeviceDirectory(value, { fallback: DEFAULT_BOOK_DIRECTORY, allowSleep: false });
const normalizeCrossPointDestination = (value) => normalizeDeviceDirectory(value, { fallback: DEFAULT_CROSSPOINT_DESTINATION, allowSleep: true });

const safeDeviceFilename = (value) => {
  const filename = String(value || '').trim();
  if (!filename || filename === '.' || filename === '..' || filename.startsWith('.') || filename.includes('/') || filename.includes('\\')) {
    throw new Error('Use a visible filename only; folders cannot be changed here.');
  }
  return filename;
};

const fileExtension = (name) => {
  const value = String(name || '').toLowerCase();
  const extension = BOOK_EXTENSIONS.find((candidate) => value.endsWith(candidate));
  return extension || '';
};
const isBookName = (name) => Boolean(fileExtension(name));
const bookTitle = (name) => String(name || '').replace(/\.(epub|xtc|xtch|txt)$/i, '').replace(/[_-]+/g, ' ');
const bookFormat = (name) => fileExtension(name).replace('.', '').toUpperCase();

const savedCrossPointDestination = () => {
  try {
    const stored = localStorage.getItem('x4-crosspoint-destination');
    // `/` was the old app default, not an intentional user choice. Migrate it
    // to the X4's standard sleep-screen folder.
    const saved = !stored || stored === '/' ? DEFAULT_CROSSPOINT_DESTINATION : stored;
    const normalized = normalizeCrossPointDestination(saved);
    if (normalized !== saved) localStorage.setItem('x4-crosspoint-destination', normalized);
    else localStorage.setItem('x4-crosspoint-destination', saved);
    return normalized;
  } catch (_) {
    localStorage.setItem('x4-crosspoint-destination', DEFAULT_CROSSPOINT_DESTINATION);
    return DEFAULT_CROSSPOINT_DESTINATION;
  }
};

const CROSSPOINT_WS_CHUNK = 4 * 1024;
const CROSSPOINT_UPLOAD_TIMEOUT_MS = 10 * 60 * 1000;

const uploadBlobViaHttp = async (host, destination, filename, blob, onProgress) => {
  const form = new FormData();
  form.append('file', blob, filename);
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), CROSSPOINT_UPLOAD_TIMEOUT_MS);
  onProgress(0, blob.size);
  try {
    const response = await fetch(`${crossPointDeviceUrl(host, '/upload')}?${new URLSearchParams({ path: destination }).toString()}`, {
      method: 'POST',
      body: form,
      signal: controller.signal,
      ...localNetworkFetchOptions(host),
    });
    await readCrossPointResponse(response);
    onProgress(blob.size, blob.size);
  } catch (error) {
    if (error?.name === 'AbortError') throw new Error(`Upload to the X4 timed out while sending ${filename}.`);
    throw localNetworkError(host, error);
  } finally {
    window.clearTimeout(timer);
  }
};

const uploadBlobViaWebSocket = (host, destination, filename, blob, onProgress) => new Promise((resolve, reject) => {
  const socket = new WebSocket(crossPointSocketUrl(host));
  socket.binaryType = 'arraybuffer';
  let settled = false;
  const finish = (error) => {
    if (settled) return;
    settled = true;
    try { socket.close(); } catch (_) { /* already closed */ }
    if (error) reject(error); else resolve();
  };
  socket.onopen = () => socket.send(`START:${filename}:${blob.size}:${destination}`);
  socket.onmessage = async (event) => {
    const message = typeof event.data === 'string' ? event.data.trim() : '';
    if (message === 'READY') {
      try {
        await new Promise((wait) => window.setTimeout(wait, 50));
        let offset = 0;
        while (offset < blob.size && socket.readyState === WebSocket.OPEN && !settled) {
          while (socket.bufferedAmount > CROSSPOINT_WS_CHUNK * 2 && socket.readyState === WebSocket.OPEN && !settled) {
            await new Promise((wait) => window.setTimeout(wait, 5));
          }
          if (settled) return;
          if (socket.readyState !== WebSocket.OPEN) throw new Error('CrossPoint closed the upload connection.');
          const end = Math.min(offset + CROSSPOINT_WS_CHUNK, blob.size);
          socket.send(await blob.slice(offset, end).arrayBuffer());
          offset = end;
          onProgress(offset, blob.size);
        }
      } catch (error) {
        finish(error);
      }
    } else if (message.startsWith('PROGRESS:')) {
      const [received, total] = message.slice('PROGRESS:'.length).split(':').map(Number);
      onProgress(received, total || blob.size);
    } else if (message === 'DONE') {
      finish();
    } else if (message.startsWith('ERROR:')) {
      finish(new Error(message.slice('ERROR:'.length) || 'CrossPoint rejected the upload.'));
    }
  };
  socket.onerror = () => finish(new Error(`Could not connect to CrossPoint at ${host}.`));
  socket.onclose = () => { if (!settled) finish(new Error('CrossPoint closed the upload connection.')); };
});

const uploadBlobToCrossPoint = async (host, destination, filename, blob, onProgress) => {
  // Callers pass an already-normalized folder. Do not run this through the
  // sleep-screen helper: that rewrites `/` to `/.sleep`.
  const httpUpload = () => uploadBlobViaHttp(host, destination, filename, blob, onProgress);
  const wsUpload = () => uploadBlobViaWebSocket(host, destination, filename, blob, onProgress);
  if (HTTPS_PAGE) {
    try {
      await httpUpload();
    } catch (httpError) {
      try {
        await wsUpload();
      } catch (_) {
        throw httpError;
      }
    }
    return;
  }
  try {
    await wsUpload();
  } catch (wsError) {
    try {
      await httpUpload();
    } catch (_) {
      throw wsError;
    }
  }
};

function ImageThumbnail({ item, large = false, censored = false }) {
  if (item.demo) return <div className={`demo-thumbnail ${large ? 'large' : ''} ${item.tone || 'paper'}`} role="img" aria-label={item.filename}><span>{item.mark || 'X4'}</span></div>;
  return <img className={censored ? 'sensitive-hidden' : ''} src={item.thumbnail_url || `/api/images/${item.id}/thumbnail`} alt={censored ? 'Hidden sensitive image' : item.filename} loading="lazy" draggable="false" />;
}

function ImageCard({ item, onInspect, selected, selectionMode, onSelect, onKeyDown, consumeSuppressedClick, showSensitive, visitor }) {
  const censored = itemIsSensitive(item) && !showSensitive;
  const handleClick = (event) => {
    if (consumeSuppressedClick?.()) return;
    if (selectionMode || event.shiftKey || event.metaKey || event.ctrlKey) {
      event.preventDefault();
      onSelect(item.id, event);
      return;
    }
    onInspect(item.id);
  };
  const label = selectionMode ? `${selected ? 'Deselect' : 'Select'} picture` : 'Open picture';
  return <article className={`image-card ${selected ? 'selected' : ''} ${selectionMode ? 'selection-mode' : ''} ${censored ? 'sensitive' : ''} ${visitor ? 'visitor' : ''}`} data-image-id={item.id}>
    <button className="image-button" onClick={handleClick} onKeyDown={(event) => onKeyDown(event, item.id)} aria-label={label} aria-pressed={selectionMode ? selected : undefined}>
      <ImageThumbnail item={item} censored={censored} />
      {selectionMode && <span className={`selection-mark ${selected ? 'active' : ''}`} aria-hidden="true">{selected ? '✓' : ''}</span>}
    </button>
    {!visitor && <div className="card-meta"><span className="card-index">{String(item.id).padStart(5, '0')}</span><span className="card-filename" title={item.filename}>{item.filename.replace(/_x4\.bmp$/i, '')}</span><span className="decision">{item.decision === 'unreviewed' ? '' : item.decision}</span></div>}
  </article>;
}

function Inspector({ item, onClose, onReview, onQueue, onTag, queued, demo, liveDevice, showSensitive, visitor }) {
  const panelRef = useRef(null);
  useEffect(() => {
    if (!item) return undefined;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const closeOnEscape = (event) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', closeOnEscape);
    const frame = window.requestAnimationFrame(() => panelRef.current?.focus());
    return () => {
      window.cancelAnimationFrame(frame);
      document.removeEventListener('keydown', closeOnEscape);
      document.body.style.overflow = previousOverflow;
    };
  }, [item?.id]);
  if (!item) return null;
  const ocrText = String(item.ocr_text || '').trim();
  const tags = [...new Map((item.tags || []).filter((tag) => tag.name).map((tag) => [tag.name, tag])).values()];
  const meanLuma = Number(item.mean_luma);
  const edgeDensity = Number(item.edge_density);
  const censored = itemIsSensitive(item) && !showSensitive;
  const downloadUrl = hostedSourceUrl(item) || item.thumbnail_url;
  const ocr = item.ocr_processed ? (ocrText || 'No English text detected.') : 'OCR has not been run for this image.';
  return <>
    <button className="inspector-backdrop" type="button" onClick={onClose} aria-label="Close picture" />
    <aside ref={panelRef} className={`inspector open ${visitor ? 'inspector-visitor' : ''}`} role="dialog" aria-modal="true" aria-labelledby="inspector-title" tabIndex="-1">
      <div className="inspector-topline"><span className="eyebrow" id="inspector-title">{visitor ? 'Picture' : `IMAGE ${String(item.id).padStart(5, '0')}`}</span><button className="close" onClick={onClose} aria-label="Close picture">×</button></div>
      <ImageThumbnail item={item} large censored={censored} />
      {visitor ? <>
        <div className="inspector-actions">
          {liveDevice && <button className="primary" type="button" onClick={() => onQueue(item.id)}>{queued ? 'Remove from send' : 'Add to send'}</button>}
        </div>
        {tags.length > 0 && <section className="inspector-section"><h3>More like this</h3><div className="tag-list">{tags.map((tag) => <button type="button" className="tag" key={tag.name} onClick={() => onTag(tag.name)}>{prettyTag(tag.name)}</button>)}</div></section>}
        {ocrText ? <section className="inspector-section"><h3>Text in this picture</h3><p className="ocr">{ocrText}</p></section> : null}
      </> : <>
        <h2>{item.filename}</h2>
        <div className="inspector-actions">
          {['keep', 'favorite', 'reject'].map((decision) => <button key={decision} className={decision === 'keep' ? 'primary' : ''} onClick={() => onReview(item.id, decision)} disabled={demo}>{decision}</button>)}
          {liveDevice && <button onClick={() => onQueue(item.id)} disabled={demo}>{queued ? 'Remove from send' : 'Add to send'}</button>}
          {downloadUrl ? <a className="ghost-link" href={downloadUrl} download={item.filename}>Download</a> : (!liveDevice && <button disabled>No file to download</button>)}
        </div>
        <section className="inspector-section"><h3>Tags</h3><div className="tag-list">{tags.length ? tags.map((tag) => <span className={`tag ${tag.source === 'machine' ? 'automatic' : ''}`} key={`${tag.name}-${tag.source}`}>{prettyTag(tag.name)}{tag.source === 'machine' && Number.isFinite(Number(tag.confidence)) ? ` · ${Number(tag.confidence).toFixed(2)}` : ''}</span>) : <span className="tag">No tags</span>}</div></section>
        <details className="inspector-details"><summary>Image details</summary><div className="facts">
          <div><span className="fact-label">STATUS</span><br />{item.decision}</div>
          <div><span className="fact-label">X4 QUALITY</span><br />{item.x4_suitability || 'unscored'}</div>
          <div><span className="fact-label">LUMA</span><br />{Number.isFinite(meanLuma) ? meanLuma.toFixed(0) : 'not reported'}</div>
          <div><span className="fact-label">EDGE DENSITY</span><br />{Number.isFinite(edgeDensity) ? `${(edgeDensity * 100).toFixed(0)}%` : 'not reported'}</div>
        </div><div className="ocr"><span className="fact-label">OCR</span><br />{ocr}</div></details>
        {item.label_evidence?.length > 0 && <details className="evidence"><summary>Model evidence ({item.label_evidence.length})</summary><div className="evidence-list">{item.label_evidence.slice(0, 40).map((evidence) => <div key={`${evidence.model}-${evidence.raw_label}`}><span>{evidence.normalized_tag || evidence.raw_label}</span><span>{evidence.accepted ? 'accepted' : 'candidate'} · {evidence.model} · {evidence.confidence_band} · {Number(evidence.score).toFixed(2)}</span></div>)}</div></details>}
      </>}
    </aside>
  </>;
}

function SendDock({ host, setHost, destination, setDestination, destinationMode, onSelectSleep, onSelectCustom, onDestinationBlur, selectedCount, visibleCount, visibleSelectedCount, imageTotal, selectionMode, onToggleSelectionMode, onClear, onUpload, onDownload, onSelectVisible, onSelectAllMatches, selectionLoading, uploading, progress, demo, liveDevice, filtered }) {
  const [expanded, setExpanded] = useState(false);
  const customDestinationMissing = destinationMode === 'custom' && !destination.trim();
  const sendLabel = !liveDevice
    ? (selectedCount ? `Download ${selectedCount}` : 'Download')
    : demo ? 'Preview' : uploading ? 'Sending…' : customDestinationMissing ? 'Choose a folder' : selectedCount ? `Send ${selectedCount} to X4` : 'Send to X4';
  useEffect(() => { if (uploading) setExpanded(true); }, [uploading]);
  if (!selectionMode && selectedCount === 0 && !uploading) return null;
  const allVisibleSelected = visibleCount > 0 && visibleSelectedCount === visibleCount;
  const outsideCount = Math.max(selectedCount - visibleSelectedCount, 0);
  const canSelectAllMatches = filtered && imageTotal > visibleCount;
  const hint = uploading && progress
    ? `${progress.index}/${progress.total} · ${Math.round((progress.received / Math.max(progress.totalBytes, 1)) * 100)}%`
    : selectedCount
      ? (outsideCount ? `${visibleSelectedCount.toLocaleString()} here · ${outsideCount.toLocaleString()} elsewhere` : 'Ready to send')
      : 'Tap a picture to add it';
  return <section className={`send-dock ${selectedCount ? 'has-selection' : ''}`} aria-label={liveDevice ? 'Send pictures to the X4' : 'Download selected pictures'} aria-live="polite">
    <div className="send-dock-copy">
      <strong>{selectedCount ? `${selectedCount.toLocaleString()} selected` : 'Select pictures'}</strong>
      <span>{hint}</span>
    </div>
    <div className="send-dock-actions">
      <button className="transfer-primary" onClick={liveDevice ? onUpload : onDownload} disabled={demo || uploading || selectedCount === 0 || (liveDevice && customDestinationMissing)}>{sendLabel}</button>
      <button type="button" className={selectionMode ? 'selection-active' : ''} onClick={onToggleSelectionMode} aria-pressed={selectionMode} disabled={uploading || visibleCount === 0}>{selectionMode ? 'Done' : 'Select'}</button>
      <button type="button" onClick={onClear} disabled={uploading || selectionLoading || selectedCount === 0}>Clear</button>
      {selectionMode && <button type="button" onClick={onSelectVisible} disabled={selectionLoading || visibleCount === 0}>{allVisibleSelected ? `Remove visible` : `Add visible`}</button>}
      {selectionMode && canSelectAllMatches && <button type="button" onClick={onSelectAllMatches} disabled={selectionLoading}>{selectionLoading ? 'Loading…' : `Add all ${imageTotal.toLocaleString()}`}</button>}
      {liveDevice && <button className="transfer-toggle" type="button" onClick={() => setExpanded((current) => !current)} aria-expanded={expanded}>Options</button>}
    </div>
    {selectionMode && <p className="selection-help">Shift range · ⌘ toggle · drag to select</p>}
    {HTTPS_PAGE && liveDevice && selectedCount > 0 && <small className="send-dock-hint">If Chrome asks, Allow this site on your Wi-Fi.</small>}
    {expanded && <div className="transfer-details">
      <div className="transfer-settings">
        <label><span>X4 ADDRESS</span><input value={host} onChange={(event) => setHost(event.target.value)} onBlur={() => { const normalized = normalizeCrossPointHost(host); setHost(normalized); localStorage.setItem('x4-crosspoint-host', normalized); }} placeholder={DEFAULT_CROSSPOINT_HOST} disabled={demo || uploading} /></label>
        <div className="destination-picker">
          <span className="setting-label">DESTINATION</span>
          <div className="destination-options">
            <button type="button" className={`destination-option ${destinationMode === 'sleep' ? 'active' : ''}`} onClick={onSelectSleep} disabled={demo || uploading} aria-pressed={destinationMode === 'sleep'}><span>Sleep screens</span></button>
            <button type="button" className={`destination-option ${destinationMode === 'custom' ? 'active' : ''}`} onClick={onSelectCustom} disabled={demo || uploading} aria-pressed={destinationMode === 'custom'}><span>Other folder</span></button>
          </div>
          {destinationMode === 'custom' && <label className="custom-destination"><span>FOLDER PATH</span><input value={destination} onChange={(event) => setDestination(event.target.value)} onBlur={onDestinationBlur} placeholder="/X4" disabled={demo || uploading} /></label>}
        </div>
      </div>
      <div className="transfer-status"><a href="/device">Device</a></div>
    </div>}
  </section>;
}

function DeviceFilePreview({ file, demo }) {
  const [requested, setRequested] = useState(false);
  if (demo) return <div className="device-file-preview device-preview-trigger"><span className="device-preview-placeholder">Preview only</span></div>;
  return requested ? <a className="device-file-preview" href={file.url} target="_blank" rel="noreferrer" aria-label={`Open ${file.name}`}>
    <img src={file.url} alt={file.name} />
  </a> : <button className="device-file-preview device-preview-trigger" onClick={() => setRequested(true)} aria-label={`Load preview for ${file.name}`}>
    <span className="device-preview-placeholder">Load preview</span>
  </button>;
}

function BookCover({ book }) {
  return <div className="book-cover" aria-hidden="true"><span>{bookFormat(book.name)}</span><strong>{book.name.slice(0, 1).toUpperCase()}</strong></div>;
}

function BookCard({ book, onRename, onMove, onDelete, demo }) {
  return <article className="book-card">
    <BookCover book={book} />
    <div className="book-card-body">
      <div className="book-card-heading"><h3 title={book.name}>{bookTitle(book.name)}</h3><span>{bookFormat(book.name)}</span></div>
      <p>{bytesLabel(book.size)} · {book.directory === '/' ? 'X4 root' : book.directory}</p>
      <div className="book-card-actions">
        {demo ? <button disabled>Preview only</button> : <a href={book.url} target="_blank" rel="noreferrer" download>Download</a>}
        <button onClick={() => onRename(book)} disabled={demo}>Rename</button>
        <button onClick={() => onMove(book)} disabled={demo}>Move</button>
        <button className="danger" onClick={() => onDelete(book)} disabled={demo}>Delete</button>
      </div>
    </div>
  </article>;
}

function BookLibrary({ books, folders, directory, loading, uploading, uploadProgress, onRefresh, onNavigate, onUpload, onMakeFolder, onRename, onMove, onDelete, canUpload, demo }) {
  const inputRef = useRef(null);
  const segments = directory === '/' ? [] : directory.split('/').filter(Boolean);
  const crumbs = segments.map((segment, index) => ({ name: segment, path: `/${segments.slice(0, index + 1).join('/')}` }));
  const handleFileChange = (event) => {
    const files = [...(event.target.files || [])];
    event.target.value = '';
    if (files.length) onUpload(files);
  };
  return <section className="bookshelf" id="books" aria-label="Books on the X4">
    <div className="bookshelf-header">
      <div><span className="transfer-kicker"><i /> BOOKS</span><h2>Books</h2><span className="book-format-note">EPUB · XTC · XTCH · TXT</span></div>
      <div className="book-header-actions">
        <button className="device-refresh" onClick={onRefresh} disabled={demo || loading || uploading}>{loading ? 'Refreshing…' : 'Refresh'}</button>
        <button className="book-primary" onClick={() => inputRef.current?.click()} disabled={demo || loading || uploading || !canUpload} title={!demo && !canUpload ? 'Connect the X4 first.' : undefined}>{demo ? 'Preview' : uploading ? 'Updating…' : 'Add books'} <span>↗</span></button>
        <input ref={inputRef} className="visually-hidden" type="file" accept={`${BOOK_EXTENSIONS.join(',')},application/epub+zip,text/plain`} multiple onChange={handleFileChange} />
      </div>
    </div>
    <div className="book-toolbar">
      <nav className="book-breadcrumbs" aria-label="Book folder">
        <button type="button" className={directory === '/' ? 'active' : ''} onClick={() => onNavigate('/')}>X4 root</button>
        {crumbs.map((crumb) => <span key={crumb.path}><b>/</b><button type="button" className={directory === crumb.path ? 'active' : ''} onClick={() => onNavigate(crumb.path)}>{crumb.name}</button></span>)}
      </nav>
      <button className="book-secondary" onClick={onMakeFolder} disabled={demo || loading || uploading}>New folder <span>+</span></button>
    </div>
    {uploadProgress && <div className="book-upload-progress" aria-live="polite"><span>{uploadProgress.index}/{uploadProgress.total} · {uploadProgress.filename}</span><strong>{Math.round((uploadProgress.received / Math.max(uploadProgress.totalBytes, 1)) * 100)}%</strong></div>}
    {folders.length > 0 && <div className="book-folders" aria-label="Book folders">{folders.map((folder) => <button className="book-folder" key={folder.path} onClick={() => onNavigate(folder.path)}><span>↳</span><strong>{folder.name}</strong><small>Open folder</small></button>)}</div>}
    {books.length > 0 ? <div className="book-grid">{books.map((book) => <BookCard key={book.path} book={book} onRename={onRename} onMove={onMove} onDelete={onDelete} demo={demo} />)}</div> : folders.length === 0 ? <div className="device-empty">No books here.</div> : null}
  </section>;
}

function SleepScreenLibrary({ files, loading, onRefresh, onRename, onDelete, demo }) {
  return <details className="sleep-panel">
    <summary><span><i /> Sleep screens</span><small>{files.length} · <code>/.sleep</code></small><b>+</b></summary>
    <div className="sleep-panel-body">
      <div className="sleep-panel-heading"><span className="section-note">Images in <code>/.sleep</code></span><button className="device-refresh" onClick={onRefresh} disabled={demo || loading}>{loading ? 'Refreshing…' : 'Refresh'}</button></div>
      {files.length ? <div className="device-file-grid">{files.map((file) => <article className="device-file" key={file.path}>
        <DeviceFilePreview file={file} demo={demo} />
        <div className="device-file-info"><strong title={file.name}>{file.name}</strong><span>{bytesLabel(file.size)}</span></div>
        <div className="device-file-actions">{demo ? <button disabled>Preview only</button> : <a href={file.url} target="_blank" rel="noreferrer">Open</a>}<button onClick={() => onRename(file)} disabled={demo}>Rename</button><button className="danger" onClick={() => onDelete(file)} disabled={demo}>Delete</button></div>
      </article>)}</div> : <div className="device-empty">No sleep screens found on the X4.</div>}
    </div>
  </details>;
}

function DeviceLibrary({ host, setHost, files, books, folders, bookDirectory, storage, status, loading, uploading, uploadProgress, error, onRefresh, onNavigateBooks, onUploadBooks, onMakeFolder, onRename, onRenameBook, onMoveBook, onDelete, onDeleteBook, demo }) {
  const listedBytes = files.reduce((sum, file) => sum + file.size, 0) + books.reduce((sum, file) => sum + file.size, 0);
  const capacityKnown = storage.freeBytes !== null;
  const storageKnown = capacityKnown && storage.totalBytes !== null && storage.usedBytes !== null;
  const usedPercent = storageKnown ? Math.min(100, Math.max(0, (storage.usedBytes / storage.totalBytes) * 100)) : 0;
  const firmware = status?.version || 'unknown';
  const apiMode = firmware === '1.5.0' ? 'CORS API' : 'loopback fallback';
  const connectionLabel = demo ? 'DEMO' : status ? 'ONLINE' : error ? 'OFFLINE' : 'CONNECTING…';
  const canUploadBooks = !demo && Boolean(status);
  return <section className="device-library" aria-label="X4 device library">
    <div className="device-library-header">
      <div>
        <a className="device-back-link device-library-back" href={HOSTED ? '/browse' : '/'}>← Catalog</a>
        <span className="transfer-kicker"><i /> DEVICE</span>
        <h2>X4</h2>
      </div>
      <div className="device-header-actions"><strong className={`device-status device-${connectionLabel.toLowerCase()}`}><i /> {connectionLabel}</strong><button className="device-refresh" onClick={onRefresh} disabled={demo || loading}>{loading ? 'Refreshing…' : 'Refresh'}</button></div>
    </div>
    <details className="device-details"><summary><span>Device info</span><small>{firmware} · {status?.serial || 'not connected'}</small><b>+</b></summary><div className="device-identity" aria-label="CrossPoint device status">
      <div><span>STATUS</span><strong className={connectionLabel === 'ONLINE' ? 'device-online' : connectionLabel === 'DEMO' ? 'device-demo' : 'device-offline'}><i /> {connectionLabel}</strong></div>
      <div><span>FIRMWARE</span><strong>{firmware}</strong></div>
      <div><span>DEVICE</span><strong>{status?.device || 'X4'}</strong></div>
      <div><span>API</span><strong>{apiMode}</strong></div>
      <div className="device-serial"><span>SERIAL</span><code>{status?.serial || 'not reported'}</code></div>
      <div className="device-host"><label className="device-host-input"><span>X4 ADDRESS</span><input value={host} onChange={(event) => { setHost(event.target.value); localStorage.setItem('x4-crosspoint-host', event.target.value); }} onBlur={() => { const normalized = normalizeCrossPointHost(host); setHost(normalized); localStorage.setItem('x4-crosspoint-host', normalized); }} disabled={demo || loading || uploading} /></label></div>
    </div></details>
    <div className="device-storage">
      <div className="storage-heading"><span>STORAGE</span><strong>{storageKnown ? `${bytesLabel(storage.freeBytes)} free` : 'Unknown'}</strong></div>
      {storageKnown ? <><div className="storage-track"><span style={{ width: `${usedPercent}%` }} /></div><div className="storage-meta"><span>{bytesLabel(storage.usedBytes)} used</span><span>{bytesLabel(storage.totalBytes)} total</span></div></> : capacityKnown ? <div className="storage-unknown">{bytesLabel(storage.freeBytes)} free. The X4 did not report total size.</div> : status ? <div className="storage-unknown">This X4 does not report free space. You can still send pictures.</div> : <div className="storage-unknown">Connect the X4 to see storage.</div>}
      <div className="storage-meta"><span>{books.length} book{books.length === 1 ? '' : 's'} · {files.length} sleep screen{files.length === 1 ? '' : 's'}</span><span>{bytesLabel(listedBytes)} listed</span></div>
    </div>
    {error && <div className="device-error">{error} <button onClick={onRefresh}>Try again</button></div>}
    <BookLibrary books={books} folders={folders} directory={bookDirectory} loading={loading} uploading={uploading} uploadProgress={uploadProgress} onRefresh={onRefresh} onNavigate={onNavigateBooks} onUpload={onUploadBooks} onMakeFolder={onMakeFolder} onRename={onRenameBook} onMove={onMoveBook} onDelete={onDeleteBook} canUpload={canUploadBooks} demo={demo} />
    <SleepScreenLibrary files={files} loading={loading} onRefresh={onRefresh} onRename={onRename} onDelete={onDelete} demo={demo} />
  </section>;
}

const VISITOR_TAG_GROUPS = Object.freeze([
  { id: 'subject', label: 'Subject', categories: ['subject'] },
  { id: 'franchise', label: 'Shows & games', categories: ['franchise'] },
  { id: 'style', label: 'Style', categories: ['style'] },
  { id: 'display', label: 'Look on the X4', categories: ['display'] },
  { id: 'intensity', label: 'Mood', categories: ['intensity'] },
]);
const CURATOR_TAG_GROUPS = Object.freeze([
  ...VISITOR_TAG_GROUPS,
  { id: 'composition', label: 'Composition', categories: ['composition'] },
  { id: 'content', label: 'Content', categories: ['content'] },
  { id: 'x4', label: 'X4 scores', categories: ['x4'] },
  { id: 'status', label: 'Status', categories: ['status'] },
  { id: 'model', label: 'Model', categories: ['model'] },
]);

const hostedMatches = (catalog, { query = '', tags = [], cluster = null, showSensitive = false } = {}) => {
  const search = query.toLowerCase();
  const required = tags.filter(Boolean);
  return (catalog?.images || []).filter((item) => {
    if (!showSensitive && itemIsSensitive(item)) return false;
    const names = new Set((item.tags || []).map((itemTag) => itemTag.name));
    const searchable = [item.filename, item.ocr_text, ...names].join(' ').toLowerCase();
    const tagHit = required.every((name) => names.has(name));
    const clusterHit = cluster == null || (item.cluster_ids || []).includes(Number(cluster));
    return (!search || searchable.includes(search)) && tagHit && clusterHit;
  });
};

function FilterBar({ query, setQuery, selectedTags, tags, groups, filtersOpen, setFiltersOpen, onToggleTag, onClearTags, onClearSearch, tagSearch, setTagSearch, tagGroup, setTagGroup, showSensitive, onToggleSensitive, hosted, cluster, onClearCluster }) {
  const available = tags.filter((item) => showSensitive || !SENSITIVE_TAGS.has(item.name));
  const populatedGroups = groups.filter((group) => available.some((item) => group.categories.includes(item.category)));
  const activeGroup = populatedGroups.find((group) => group.id === tagGroup) || populatedGroups[0];
  const needle = tagSearch.trim().toLowerCase();
  const choices = (needle
    ? available.filter((item) => item.name.includes(needle) || prettyTag(item.name).toLowerCase().includes(needle))
    : available.filter((item) => activeGroup && activeGroup.categories.includes(item.category))
  ).slice().sort((a, b) => (b.automatic_count || 0) - (a.automatic_count || 0)).slice(0, 60);
  const hasActive = selectedTags.length > 0 || Boolean(query) || cluster != null;
  return <section className="control-room" aria-label="Find pictures">
    <label className="searchbox"><span>SEARCH</span><input type="search" aria-label="Search pictures" placeholder="Search pictures" value={query} onChange={(event) => { onClearCluster?.(); setQuery(event.target.value); }} /></label>
    {hasActive && <div className="filter-chips" aria-label="Active filters">
      {query && <button type="button" className="filter-chip" onClick={onClearSearch}><span>Search · {query}</span><b aria-hidden="true">×</b></button>}
      {selectedTags.map((name, index) => <span className="filter-chip-wrap" key={name}>{index > 0 && <i className="filter-and">and</i>}<button type="button" className="filter-chip" onClick={() => onToggleTag(name)}><span>{prettyTag(name)}</span><b aria-hidden="true">×</b></button></span>)}
      {selectedTags.length > 1 && <button type="button" className="filter-clear" onClick={onClearTags}>Clear filters</button>}
    </div>}
    <div className="control-toolbar">
      <button type="button" className={`filter-toggle ${filtersOpen ? 'open' : ''}`} onClick={() => setFiltersOpen((current) => !current)} aria-expanded={filtersOpen} aria-controls="filter-drawer">{selectedTags.length ? `Filter · ${selectedTags.length}` : 'Filter'}<b aria-hidden="true">{filtersOpen ? '−' : '+'}</b></button>
      {hosted && <button type="button" className="nsfw-toggle" aria-pressed={showSensitive} onClick={onToggleSensitive}>{showSensitive ? 'NSFW is on' : 'Show NSFW'}</button>}
    </div>
    {filtersOpen && <div className="filter-picker" id="filter-drawer">
      <label className="tag-search"><span>FIND A FILTER</span><input type="search" aria-label="Find a filter" placeholder="batman, dark, manga…" value={tagSearch} onChange={(event) => setTagSearch(event.target.value)} /></label>
      {!needle && populatedGroups.length > 0 && <div className="filter-groups" role="tablist" aria-label="Filter groups">
        {populatedGroups.map((group) => <button type="button" role="tab" key={group.id} className={activeGroup?.id === group.id ? 'active' : ''} aria-selected={activeGroup?.id === group.id} onClick={() => setTagGroup(group.id)}>{group.label}</button>)}
      </div>}
      <div className="filter-choices">
        {choices.length ? choices.map((item) => <button type="button" key={item.name} className={`filter-choice ${selectedTags.includes(item.name) ? 'active' : ''}`} onClick={() => onToggleTag(item.name)}>{prettyTag(item.name)} <small>{item.automatic_count || 0}</small></button>) : <p className="filter-empty">No filters match that.</p>}
      </div>
    </div>}
  </section>;
}

function HomePage({ imageCount }) {
  return <article className="product-home">
    <span className="product-kicker">XTEINK X4</span>
    <h1>X4 Catalog</h1>
    <p className="lede">Pictures for the X4 sleep screen. Look around here. Send them to your device over your own Wi-Fi.</p>
    <div className="product-actions">
      <a className="primary" href="/browse">Browse pictures</a>
      <a href="/docs">How to send to your X4</a>
      <a href={GITHUB_URL}>Source on GitHub</a>
    </div>
    <div className="product-grid">
      <article><h2>Look</h2><p>{imageCount ? `${imageCount.toLocaleString()} images` : 'A public set of pictures'} sized for the X4. NSFW stays hidden unless you turn it on.</p></article>
      <article><h2>Send</h2><p>On the X4 home screen, open <strong>File Transfer</strong>. Same Wi-Fi as this computer. The pictures go straight to the device.</p></article>
      <article><h2>Your own library</h2><p>Want your own folder of BMPs, tags, and reviews? Run the same software on your computer. That never changes your original files.</p></article>
    </div>
  </article>;
}

function DeviceHowTo() {
  return <p className="howto-line">On the X4, open <strong>File Transfer</strong>. Same Wi-Fi. Pictures from <a href={HOSTED ? '/browse' : '/'}>Browse</a>. Books with Add books below. <a href="/docs">Guide</a></p>;
}

function DocsPage() {
  return <article className="docs-page">
    <span className="product-kicker">Guide</span>
    <h1>Send pictures to your X4</h1>
    <p className="lede">You do not need to install anything. On the X4, File Transfer is the CrossPoint screen that talks over Wi-Fi. Pictures go from this site to the X4. They do not pass through our servers.</p>
    <h2>What you need</h2>
    <ul>
      <li>An XTEINK X4 with CrossPoint, turned on</li>
      <li>This computer or phone on the <strong>same Wi-Fi</strong> as the X4</li>
      <li>Chrome, if you can. Safari often says no.</li>
    </ul>
    <h2>Do this</h2>
    <ol>
      <li>On the X4 <strong>home screen</strong>, open <strong>File Transfer</strong>. That is CrossPoint. You should see an address such as <code>crosspoint.local</code> or numbers like <code>192.168.1.20</code>.</li>
      <li>On this computer, open the <a href="/device">Device</a> page.</li>
      <li>Type that address in <strong>X4 address</strong>.</li>
      <li>Click <strong>Refresh</strong>.</li>
      <li>If a popup asks to use a device on your local network, click <strong>Allow</strong>.</li>
      <li>When the page says <strong>Online</strong>, go to <a href={HOSTED ? '/browse' : '/'}>Browse</a>.</li>
      <li>Tap <strong>Select</strong>, pick pictures, then <strong>Send to X4</strong>.</li>
    </ol>
    <h2>If it does not connect</h2>
    <ul>
      <li>Stay on the same Wi-Fi. Guest Wi-Fi and phone hotspots often block this.</li>
      <li>Try the numbers from File Transfer, not the name.</li>
      <li>Use Chrome. Safari and Firefox may block it.</li>
      <li>Click Allow if the browser asks. If you clicked Block, refresh and try again.</li>
    </ul>
    <p>Sleep screens go to the X4 sleep folder. Books go on the <a href="/device">Device</a> page: <strong>Add books</strong>. EPUB, XTC, XTCH, or TXT.</p>
    <h2>CrossPoint help</h2>
    <p>File Transfer, Wi-Fi, and the rest of the X4 screens are documented by CrossPoint: <a href={CROSSPOINT_GUIDE_URL}>user guide</a> and <a href={CROSSPOINT_REPO_URL}>source</a>.</p>
    <h2>Want it to always work?</h2>
    <p>Run X4 Catalog on your computer and open <a href="http://127.0.0.1:8765">http://127.0.0.1:8765</a>. That path does not need the browser popup. Install steps are in the <a href={`${GITHUB_URL}/blob/main/README.md`}>README</a>.</p>
    <p>Why the popup exists, firmware notes, and WebSocket limits: <a href={`${GITHUB_URL}/blob/main/docs/device.md`}>docs/device.md</a>.</p>
  </article>;
}

function SiteFooter() {
  return <footer className="site-footer">
    <span>X4 Catalog · Unlicense</span>
    <nav aria-label="Footer">
      <a href="/docs">How to</a>
      <a href={GITHUB_URL}>GitHub</a>
      <a href={`${GITHUB_URL}/blob/main/PRIVACY.md`}>Privacy</a>
      <a href={`${GITHUB_URL}/blob/main/CONTENT.md`}>Content</a>
    </nav>
  </footer>;
}

function App() {
  const [hostedCatalog, setHostedCatalog] = useState(null);
  const [images, setImages] = useState([]);
  const [imageTotal, setImageTotal] = useState(0);
  const [imageOffset, setImageOffset] = useState(0);
  const [imageLoading, setImageLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [inspected, setInspected] = useState(null);
  const [query, setQuery] = useState('');
  const [selectedTags, setSelectedTags] = useState([]);
  const [tagSearch, setTagSearch] = useState('');
  const [tagGroup, setTagGroup] = useState('subject');
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [tags, setTags] = useState([]);
  const [cluster, setCluster] = useState(null);
  const [mode, setMode] = useState('images');
  const [clusters, setClusters] = useState([]);
  const [notice, setNotice] = useState('');
  const [showSensitive, setShowSensitive] = useState(savedShowSensitive);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [selectionMode, setSelectionMode] = useState(false);
  const [selectionAnchorId, setSelectionAnchorId] = useState(null);
  const [selectionLoading, setSelectionLoading] = useState(false);
  const [marquee, setMarquee] = useState(null);
  const [crosspointHost, setCrosspointHost] = useState(savedCrossPointHost);
  const [crosspointDestination, setCrosspointDestination] = useState(savedCrossPointDestination);
  const [crosspointDestinationMode, setCrosspointDestinationMode] = useState(() => savedCrossPointDestination() === DEFAULT_CROSSPOINT_DESTINATION ? 'sleep' : 'custom');
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(null);
  const [rebuilding, setRebuilding] = useState(false);
  const [deviceFiles, setDeviceFiles] = useState([]);
  const [deviceBooks, setDeviceBooks] = useState([]);
  const [deviceFolders, setDeviceFolders] = useState([]);
  const [bookDirectory, setBookDirectory] = useState(DEFAULT_BOOK_DIRECTORY);
  const [bookUploading, setBookUploading] = useState(false);
  const [bookUploadProgress, setBookUploadProgress] = useState(null);
  const [deviceStatus, setDeviceStatus] = useState(null);
  const [deviceStorage, setDeviceStorage] = useState({ totalBytes: null, usedBytes: null, freeBytes: null });
  const [deviceLoading, setDeviceLoading] = useState(false);
  const [deviceError, setDeviceError] = useState('');
  const imageRequestRef = useRef(0);
  const galleryRef = useRef(null);
  const dragStartRef = useRef(null);
  const marqueeArmedRef = useRef(false);
  const suppressClickRef = useRef(false);

  const loadImages = async ({ append = false } = {}) => {
    const requestId = ++imageRequestRef.current;
    const offset = append ? imageOffset : 0;
    if (append) setLoadingMore(true); else setImageLoading(true);
    if (PUBLIC_DEMO || HOSTED) {
      const result = PUBLIC_DEMO
        ? DEMO_IMAGES.filter((item) => {
            const searchable = [item.filename, item.ocr_text, ...item.tags.map((itemTag) => itemTag.name)].join(' ').toLowerCase();
            return (!query.toLowerCase() || searchable.includes(query.toLowerCase())) && selectedTags.every((name) => item.tags.some((itemTag) => itemTag.name === name));
          })
        : hostedMatches(hostedCatalog, { query, tags: selectedTags, cluster, showSensitive });
      const sliced = result.slice(offset, offset + IMAGE_PAGE_SIZE);
      if (requestId === imageRequestRef.current) {
        setImages((current) => append ? [...current, ...sliced] : sliced);
        setImageTotal(result.length);
        setImageOffset(offset + sliced.length);
        setImageLoading(false);
        setLoadingMore(false);
      }
      return { items: sliced, total: result.length, limit: IMAGE_PAGE_SIZE, offset };
    }
    const params = new URLSearchParams({ limit: String(IMAGE_PAGE_SIZE), offset: String(offset) });
    if (query) params.set('q', query);
    if (selectedTags.length === 1) params.set('tag', selectedTags[0]);
    if (selectedTags.length > 1) params.set('tags', selectedTags.join(','));
    if (cluster) params.set('cluster_id', cluster);
    try {
      const result = await get(`/api/images?${params}`);
      if (requestId !== imageRequestRef.current) return result;
      const nextItems = result.items || [];
      setImages((current) => append ? [...current, ...nextItems] : nextItems);
      setImageTotal(Number(result.total) || nextItems.length);
      setImageOffset(offset + nextItems.length);
      return result;
    } finally {
      if (requestId === imageRequestRef.current) {
        setImageLoading(false);
        setLoadingMore(false);
      }
    }
  };
  const loadClusters = async () => {
    if (PUBLIC_DEMO) {
      setClusters(DEMO_CLUSTERS);
      return DEMO_CLUSTERS;
    }
    if (HOSTED) {
      const result = hostedCatalog?.clusters || [];
      setClusters(result);
      return result;
    }
    const result = (await get('/api/clusters')).items;
    setClusters(result);
    return result;
  };
  const loadTags = async () => {
    if (PUBLIC_DEMO || HOSTED) {
      const source = PUBLIC_DEMO ? DEMO_TAGS : (hostedCatalog?.tags || []);
      setTags(source.filter((item) => showSensitive || !SENSITIVE_TAGS.has(item.name)));
      return source;
    }
    setTags((await get('/api/tags?limit=500')).items);
  };
  const loadBookDirectory = async (directory = bookDirectory) => {
    const normalized = normalizeBookDirectory(directory);
    if (PUBLIC_DEMO) {
      const result = DEMO_BOOK_LISTINGS[normalized] || { folders: [], books: [] };
      setBookDirectory(normalized);
      setDeviceBooks(result.books);
      setDeviceFolders(result.folders);
      return result;
    }
    const listed = await crossPointRequest(crosspointHost, `/api/files?path=${encodeURIComponent(normalized)}`);
    const items = Array.isArray(listed) ? listed : listed?.files || [];
    const folders = items.filter((item) => item.isDirectory && item.name && !String(item.name).startsWith('.')).map((item) => ({
      name: String(item.name),
      path: joinDevicePath(normalized, String(item.name)),
    }));
    const books = items.filter((item) => !item.isDirectory && isBookName(item.name)).map((item) => {
      const name = String(item.name);
      const path = joinDevicePath(normalized, name);
      return { name, size: Number(item.size) || 0, path, directory: normalized, url: deviceFileUrl(crosspointHost, path) };
    });
    setBookDirectory(normalized);
    setDeviceBooks(books);
    setDeviceFolders(folders);
    return { books, folders };
  };
  const loadDevice = async () => {
    setDeviceLoading(true);
    setDeviceError('');
    setDeviceStatus(null);
    try {
      if (PUBLIC_DEMO) {
        const files = DEMO_SLEEP_FILES;
        const status = DEMO_STATUS;
        const booksResult = await loadBookDirectory(bookDirectory);
        const listedBytes = files.reduce((sum, file) => sum + file.size, 0) + booksResult.books.reduce((sum, file) => sum + file.size, 0);
        const storage = parseDeviceStorage(status, null, listedBytes);
        setDeviceStatus(status);
        setDeviceFiles(files);
        setDeviceStorage(storage);
        return { status, files, storage, books: booksResult.books };
      }
      // The embedded webserver is single-client oriented; keep these requests
      // sequential so a directory refresh cannot race the status request.
      const status = await crossPointRequest(crosspointHost, '/api/status');
      const listed = await crossPointRequest(crosspointHost, `/api/files?path=${encodeURIComponent(DEFAULT_CROSSPOINT_DESTINATION)}`);
      const items = Array.isArray(listed) ? listed : listed?.files || [];
      const files = items.filter((item) => !item.isDirectory).map((item) => ({
        name: String(item.name),
        size: Number(item.size) || 0,
        path: joinDevicePath(DEFAULT_CROSSPOINT_DESTINATION, String(item.name)),
        url: deviceFileUrl(crosspointHost, joinDevicePath(DEFAULT_CROSSPOINT_DESTINATION, String(item.name))),
      }));
      const booksResult = await loadBookDirectory(bookDirectory);
      const listedBytes = files.reduce((sum, file) => sum + file.size, 0) + booksResult.books.reduce((sum, file) => sum + file.size, 0);
      const storage = parseDeviceStorage(status, null, listedBytes);
      setDeviceStatus(status);
      setDeviceFiles(files);
      setDeviceStorage(storage);
      return { status, files, storage, books: booksResult.books };
    } catch (error) {
      setDeviceError(error.message);
      throw error;
    } finally {
      setDeviceLoading(false);
    }
  };
  useEffect(() => {
    if (!HOSTED) return undefined;
    fetch('/catalog-url.json')
      .then((response) => {
        if (!response.ok) throw new Error('Catalog has not been published yet. Run x4catalog publish locally.');
        return response.json();
      })
      .then((meta) => {
        const catalogUrl = meta.url || '/catalog.json';
        return fetch(catalogUrl.includes('?') ? catalogUrl : `${catalogUrl}?v=${encodeURIComponent(meta.updated || '1')}`);
      })
      .then((response) => {
        if (!response.ok) throw new Error('Could not load the published catalog snapshot.');
        return response.json();
      })
      .then(setHostedCatalog)
      .catch((error) => setNotice(error.message));
    return undefined;
  }, []);
  useEffect(() => {
    const titles = { home: 'X4 Catalog', browse: 'Browse · X4 Catalog', device: 'Device · X4 Catalog', docs: 'Docs · X4 Catalog' };
    document.title = titles[PAGE] || 'X4 Catalog';
  }, []);
  useEffect(() => {
    if (DEVICE_PAGE) {
      if (!LIVE_DEVICE && !PUBLIC_DEMO) {
        setDeviceError('This HTTPS site cannot reach CrossPoint. Open the local catalog at http://127.0.0.1:8765 to talk to an X4.');
        return undefined;
      }
      loadDevice().catch((error) => setNotice(error.message));
      return undefined;
    }
    if (!LIVE_DEVICE || selectedIds.size === 0) return undefined;
    loadDevice().catch(() => {
      // The transfer bar displays the safe, storage-unverified state.
    });
    return undefined;
  }, [selectedIds.size]);
  useEffect(() => {
    if (DEVICE_PAGE || PAGE === 'home' || PAGE === 'docs') return undefined;
    if (HOSTED && !hostedCatalog) return undefined;
    const timer = window.setTimeout(() => loadTags().catch((error) => setNotice(error.message)), 160);
    return () => window.clearTimeout(timer);
  }, [hostedCatalog, showSensitive]);
  useEffect(() => {
    if (DEVICE_PAGE || PAGE === 'home' || PAGE === 'docs' || mode !== 'images') return undefined;
    if (HOSTED && !hostedCatalog) return undefined;
    const timer = window.setTimeout(() => loadImages().catch((error) => setNotice(error.message)), 180);
    return () => window.clearTimeout(timer);
  }, [query, selectedTags, cluster, mode, hostedCatalog, showSensitive]);
  useEffect(() => { if (SHOW_CLUSTERS && mode === 'clusters') loadClusters().catch((error) => setNotice(error.message)); }, [mode, hostedCatalog]);

  useEffect(() => {
    const updateMarquee = (event) => {
      const start = dragStartRef.current;
      if (!start || !isFinePointer(event)) return;
      if (start.id != null && event.pointerId !== start.id) return;
      const width = Math.abs(event.clientX - start.x);
      const height = Math.abs(event.clientY - start.y);
      if (!marqueeArmedRef.current) {
        if (width <= 6 && height <= 6) return;
        marqueeArmedRef.current = true;
        suppressClickRef.current = true;
      }
      event.preventDefault();
      setMarquee({ left: Math.min(start.x, event.clientX), top: Math.min(start.y, event.clientY), width, height });
    };
    const finishMarquee = (event) => {
      const start = dragStartRef.current;
      if (!start) return;
      if (event.type === 'pointercancel' || (event.pointerType && !isFinePointer(event))) {
        dragStartRef.current = null;
        marqueeArmedRef.current = false;
        setMarquee(null);
        return;
      }
      if (start.id != null && event.pointerId != null && event.pointerId !== start.id) return;
      const left = Math.min(start.x, event.clientX);
      const top = Math.min(start.y, event.clientY);
      const width = Math.abs(event.clientX - start.x);
      const height = Math.abs(event.clientY - start.y);
      if (marqueeArmedRef.current && (width > 6 || height > 6)) {
        const selectedInMarquee = [...(galleryRef.current?.querySelectorAll('.image-card') || [])]
          .filter((card) => {
            const rect = card.getBoundingClientRect();
            return rect.right >= left && rect.left <= left + width && rect.bottom >= top && rect.top <= top + height;
          })
          .map((card) => Number(card.dataset.imageId))
          .filter(Number.isFinite);
        if (selectedInMarquee.length) {
          setSelectedIds((current) => new Set([...current, ...selectedInMarquee]));
          setSelectionAnchorId(selectedInMarquee[selectedInMarquee.length - 1]);
          setSelectionMode(true);
        }
      }
      dragStartRef.current = null;
      marqueeArmedRef.current = false;
      setMarquee(null);
    };
    window.addEventListener('pointermove', updateMarquee, { passive: false });
    window.addEventListener('pointerup', finishMarquee, true);
    window.addEventListener('mouseup', finishMarquee, true);
    window.addEventListener('pointercancel', finishMarquee, true);
    return () => {
      window.removeEventListener('pointermove', updateMarquee);
      window.removeEventListener('pointerup', finishMarquee, true);
      window.removeEventListener('mouseup', finishMarquee, true);
      window.removeEventListener('pointercancel', finishMarquee, true);
    };
  }, []);

  const inspect = async (id) => {
    if (PUBLIC_DEMO) {
      setInspected(DEMO_IMAGES.find((item) => item.id === id) || null);
      return;
    }
    if (HOSTED) {
      setInspected((hostedCatalog?.images || []).find((item) => item.id === id) || null);
      return;
    }
    try { setInspected(await get(`/api/images/${id}`)); } catch (error) { setNotice(error.message); }
  };
  const toggleSelectionMode = () => setSelectionMode((current) => !current);
  const selectImage = (id, event = {}) => {
    const range = event.shiftKey && selectionAnchorId !== null;
    const toggle = event.metaKey || event.ctrlKey || selectionMode;
    setSelectedIds((current) => {
      const next = new Set(current);
      if (range) {
        const visibleIds = images.map((item) => item.id);
        const anchorIndex = visibleIds.indexOf(selectionAnchorId);
        const targetIndex = visibleIds.indexOf(id);
        if (anchorIndex >= 0 && targetIndex >= 0) {
          const start = Math.min(anchorIndex, targetIndex);
          const end = Math.max(anchorIndex, targetIndex);
          visibleIds.slice(start, end + 1).forEach((visibleId) => next.add(visibleId));
        } else if (toggle) {
          if (next.has(id)) next.delete(id); else next.add(id);
        } else {
          next.add(id);
        }
      } else if (toggle) {
        if (next.has(id)) next.delete(id); else next.add(id);
      } else {
        next.add(id);
      }
      return next;
    });
    setSelectionAnchorId(id);
    setSelectionMode(true);
  };
  const visibleSelectedCount = images.reduce((count, item) => count + (selectedIds.has(item.id) ? 1 : 0), 0);
  const selectVisible = () => {
    const visibleIds = images.map((item) => item.id);
    const allVisibleSelected = visibleIds.length > 0 && visibleIds.every((id) => selectedIds.has(id));
    setSelectedIds((current) => {
      const next = new Set(current);
      visibleIds.forEach((id) => (allVisibleSelected ? next.delete(id) : next.add(id)));
      return next;
    });
    if (visibleIds.length) setSelectionAnchorId(visibleIds[visibleIds.length - 1]);
    setSelectionMode(true);
  };
  const selectAllMatches = async () => {
    if (selectionLoading) return;
    setSelectionLoading(true);
    try {
      let ids;
      if (PUBLIC_DEMO) {
        ids = images.map((item) => item.id);
      } else if (HOSTED) {
        ids = hostedMatches(hostedCatalog, { query, tags: selectedTags, cluster, showSensitive }).map((item) => item.id);
      } else {
        const params = new URLSearchParams();
        if (query) params.set('q', query);
        if (selectedTags.length === 1) params.set('tag', selectedTags[0]);
        if (selectedTags.length > 1) params.set('tags', selectedTags.join(','));
        if (cluster) params.set('cluster_id', cluster);
        const result = await get(`/api/images/ids${params.toString() ? `?${params}` : ''}`);
        ids = result.ids || [];
      }
      setSelectedIds((current) => new Set([...current, ...ids]));
      if (ids.length) setSelectionAnchorId(ids[ids.length - 1]);
      setSelectionMode(true);
      setNotice(`Added ${ids.length.toLocaleString()} matching image${ids.length === 1 ? '' : 's'} to the selection.`);
    } catch (error) {
      setNotice(error.message);
    } finally {
      setSelectionLoading(false);
    }
  };
  const clearSelection = ({ exit = false } = {}) => {
    setSelectedIds(new Set());
    setSelectionAnchorId(null);
    if (exit) setSelectionMode(false);
  };
  const queueFromInspector = (id) => {
    const adding = !selectedIds.has(id);
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
    setSelectionAnchorId(id);
    setSelectionMode(true);
    if (HOSTED && adding) setInspected(null);
  };
  const toggleTag = (name) => {
    setCluster(null);
    setSelectedTags((current) => current.includes(name) ? current.filter((item) => item !== name) : [...current, name]);
  };
  const filterFromInspector = (name) => {
    setCluster(null);
    setSelectedTags((current) => current.includes(name) ? current : [...current, name]);
    setInspected(null);
  };
  const selectCluster = async (clusterId) => {
    if (selectionLoading) return;
    setSelectionLoading(true);
    try {
      let ids;
      if (PUBLIC_DEMO) {
        ids = DEMO_IMAGES.map((item) => item.id);
      } else if (HOSTED) {
        ids = hostedMatches(hostedCatalog, { cluster: clusterId, showSensitive }).map((item) => item.id);
      } else {
        const result = await get(`/api/images/ids?cluster_id=${encodeURIComponent(clusterId)}`);
        ids = result.ids || [];
      }
      setSelectedIds((current) => new Set([...current, ...ids]));
      if (ids.length) setSelectionAnchorId(ids[ids.length - 1]);
      setQuery('');
      setSelectedTags([]);
      setCluster(clusterId);
      setMode('images');
      setSelectionMode(true);
      setNotice(`Added ${ids.length.toLocaleString()} cluster image${ids.length === 1 ? '' : 's'} to the selection.`);
    } catch (error) {
      setNotice(error.message);
    } finally {
      setSelectionLoading(false);
    }
  };
  const consumeSuppressedClick = () => {
    if (!suppressClickRef.current) return false;
    suppressClickRef.current = false;
    return true;
  };
  const moveImageFocus = (id, key) => {
    const buttons = [...(galleryRef.current?.querySelectorAll('.image-button') || [])];
    const currentIndex = buttons.findIndex((button) => Number(button.closest('.image-card')?.dataset.imageId) === id);
    if (currentIndex < 0) return;
    let targetIndex = currentIndex;
    if (key === 'ArrowLeft') targetIndex = Math.max(0, currentIndex - 1);
    if (key === 'ArrowRight') targetIndex = Math.min(buttons.length - 1, currentIndex + 1);
    if (key === 'ArrowUp' || key === 'ArrowDown') {
      const currentRect = buttons[currentIndex].getBoundingClientRect();
      const direction = key === 'ArrowUp' ? -1 : 1;
      const candidates = buttons.map((button, index) => ({ index, rect: button.getBoundingClientRect() })).filter(({ index, rect }) => {
        if (index === currentIndex) return false;
        const verticalDistance = rect.top - currentRect.top;
        return direction > 0 ? verticalDistance > 4 : verticalDistance < -4;
      });
      candidates.sort((a, b) => Math.abs(a.rect.left - currentRect.left) + Math.abs(a.rect.top - currentRect.top) - (Math.abs(b.rect.left - currentRect.left) + Math.abs(b.rect.top - currentRect.top)));
      if (candidates[0]) targetIndex = candidates[0].index;
    }
    buttons[targetIndex]?.focus();
  };
  const handleImageKeyDown = (event, id) => {
    if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) {
      event.preventDefault();
      moveImageFocus(id, event.key);
      return;
    }
    if (selectionMode && (event.key === ' ' || event.key === 'Enter')) {
      event.preventDefault();
      selectImage(id, event);
    }
  };
  const handleGalleryPointerDown = (event) => {
    if (!selectionMode || event.button !== 0 || !isFinePointer(event)) return;
    dragStartRef.current = { x: event.clientX, y: event.clientY, id: event.pointerId };
    marqueeArmedRef.current = false;
  };
  const handleGalleryKeyDown = (event) => {
    const target = event.target;
    if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target.isContentEditable) return;
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'a') {
      event.preventDefault();
      selectAllMatches();
    } else if (event.key === 'Escape' && selectionMode) {
      setSelectionMode(false);
    }
  };
  const selectSleepDestination = () => {
    setCrosspointDestinationMode('sleep');
    setCrosspointDestination(DEFAULT_CROSSPOINT_DESTINATION);
  };
  const selectCustomDestination = () => {
    setCrosspointDestinationMode('custom');
    if (crosspointDestination === DEFAULT_CROSSPOINT_DESTINATION) setCrosspointDestination('');
  };
  const normalizeDestinationField = () => {
    if (crosspointDestinationMode === 'custom' && !crosspointDestination.trim()) return;
    try {
      setCrosspointDestination(normalizeCrossPointDestination(crosspointDestination));
    } catch (error) {
      setCrosspointDestination('');
      setNotice(error.message);
    }
  };
  const renameOnDevice = async (file, { book = false } = {}) => {
    if (PUBLIC_DEMO) {
      setNotice('This public preview is read-only.');
      return;
    }
    const nextName = window.prompt(`Rename ${file.name} on the X4`, file.name)?.trim();
    if (!nextName || nextName === file.name) return;
    try {
      const safeName = safeDeviceFilename(nextName);
      if (book && !isBookName(safeName)) throw new Error('Keep a supported book extension: .epub, .xtc, .xtch, or .txt.');
      await crossPointRequest(crosspointHost, '/rename', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ host: crosspointHost, path: file.path, name: safeName }) });
      setNotice(`Renamed ${file.name} on the X4.`);
      await loadDevice();
    } catch (error) {
      setDeviceError(error.message);
      setNotice(error.message);
    }
  };
  const renameDeviceFile = (file) => renameOnDevice(file);
  const renameBook = (file) => renameOnDevice(file, { book: true });
  const deleteOnDevice = async (file, label) => {
    if (PUBLIC_DEMO) {
      setNotice('This public preview is read-only.');
      return;
    }
    if (!window.confirm(`Delete ${file.name} from the X4 ${label}? This cannot be undone.`)) return;
    try {
      await crossPointRequest(crosspointHost, '/delete', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ host: crosspointHost, path: file.path }) });
      setNotice(`Deleted ${file.name} from the X4.`);
      await loadDevice();
    } catch (error) {
      setDeviceError(error.message);
      setNotice(error.message);
    }
  };
  const deleteDeviceFile = async (file) => {
    return deleteOnDevice(file, '/.sleep');
  };
  const deleteBook = (file) => deleteOnDevice(file, 'book library');
  const navigateBooks = async (directory) => {
    try {
      setDeviceError('');
      await loadBookDirectory(directory);
    } catch (error) {
      setDeviceError(error.message);
      setNotice(error.message);
    }
  };
  const makeBookFolder = async () => {
    if (PUBLIC_DEMO) {
      setNotice('This public preview is read-only.');
      return;
    }
    const input = window.prompt('New folder name on the X4');
    if (!input) return;
    try {
      const name = safeDeviceFilename(input);
      await crossPointRequest(crosspointHost, '/mkdir', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ host: crosspointHost, path: bookDirectory, name }) });
      setNotice(`Created ${name} on the X4.`);
      await loadBookDirectory(bookDirectory);
    } catch (error) {
      setDeviceError(error.message);
      setNotice(error.message);
    }
  };
  const moveBook = async (file) => {
    if (PUBLIC_DEMO) {
      setNotice('This public preview is read-only.');
      return;
    }
    const input = window.prompt(`Move ${file.name} to a visible X4 folder`, bookDirectory);
    if (input === null) return;
    try {
      const destination = normalizeBookDirectory(input);
      if (destination === file.directory) {
        setNotice('That book is already in this folder.');
        return;
      }
      await crossPointRequest(crosspointHost, '/move', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ host: crosspointHost, path: file.path, dest: destination }) });
      setNotice(`Moved ${file.name} to ${destination}.`);
      await loadDevice();
    } catch (error) {
      setDeviceError(error.message);
      setNotice(error.message);
    }
  };
  const uploadBooks = async (files) => {
    if (PUBLIC_DEMO) {
      setNotice('This public preview is read-only.');
      return;
    }
    const candidates = files.filter((file) => isBookName(file.name));
    const rejected = files.filter((file) => !isBookName(file.name));
    if (rejected.length) setNotice(`Skipped ${rejected.length} unsupported file${rejected.length === 1 ? '' : 's'}. Choose EPUB, XTC, XTCH, or TXT books.`);
    if (!candidates.length || bookUploading) return;
    setBookUploading(true);
    setBookUploadProgress(null);
    try {
      const destination = normalizeBookDirectory(bookDirectory);
      const device = await loadDevice();
      const existing = new Map((device.books || []).map((book) => [book.name.toLowerCase(), book]));
      const replacements = candidates.filter((file) => existing.has(file.name.toLowerCase())).map((file) => file.name);
      if (replacements.length && !window.confirm(`Replace ${replacements.join(', ')} on the X4? Its EPUB cache will be refreshed.`)) return;
      const requiredBytes = candidates.reduce((sum, file) => sum + file.size + (64 * 1024), 0);
      if (device.storage.freeBytes !== null && requiredBytes > device.storage.freeBytes) {
        setNotice(`Upload blocked: ${bytesLabel(requiredBytes)} required, but only ${bytesLabel(device.storage.freeBytes)} is free on the X4.`);
        return;
      }
      localStorage.setItem('x4-crosspoint-host', crosspointHost);
      for (let index = 0; index < candidates.length; index += 1) {
        const file = candidates[index];
        const safeName = safeDeviceFilename(file.name);
        await uploadBlobToCrossPoint(crosspointHost, destination, safeName, file, (received, totalBytes) => setBookUploadProgress({ index: index + 1, total: candidates.length, filename: safeName, received, totalBytes }));
      }
      setNotice(`Added ${candidates.length} book${candidates.length === 1 ? '' : 's'} to ${destination}.`);
      await loadDevice();
    } catch (error) {
      setDeviceError(error.message);
      setNotice(error.message);
    } finally {
      setBookUploading(false);
      setBookUploadProgress(null);
    }
  };
  const downloadSelected = async () => {
    const ids = [...selectedIds];
    if (!ids.length) return;
    const catalogImages = hostedCatalog?.images || images;
    const details = ids.map((id) => catalogImages.find((item) => item.id === id)).filter(Boolean);
    const downloadable = details.map((item) => ({ ...item, href: hostedSourceUrl(item) || item.thumbnail_url })).filter((item) => item.href);
    if (!downloadable.length) {
      setNotice('Original BMPs are not in this snapshot. Run the local catalog to send them to an X4.');
      return;
    }
    if (downloadable.length > 8 && !window.confirm(`Download ${downloadable.length} files one by one?`)) return;
    for (const item of downloadable) {
      const link = document.createElement('a');
      link.href = item.href;
      link.download = item.filename || 'x4-image';
      link.rel = 'noreferrer';
      document.body.appendChild(link);
      link.click();
      link.remove();
      await new Promise((resolve) => window.setTimeout(resolve, 120));
    }
    setNotice(`Started ${downloadable.length} download${downloadable.length === 1 ? '' : 's'}. To send them to an X4, run the local catalog on http://127.0.0.1:8765.`);
  };
  const uploadSelected = async () => {
    if (!LIVE_DEVICE) {
      await downloadSelected();
      return;
    }
    if (PUBLIC_DEMO) {
      setNotice('This public preview is read-only.');
      return;
    }
    const ids = [...selectedIds];
    if (!ids.length || uploading) return;
    if (crosspointDestinationMode === 'custom' && !crosspointDestination.trim()) {
      setNotice('Choose a custom CrossPoint folder before sending.');
      return;
    }
    let destination;
    try {
      destination = normalizeCrossPointDestination(crosspointDestinationMode === 'sleep' ? DEFAULT_CROSSPOINT_DESTINATION : crosspointDestination);
    } catch (error) {
      setNotice(error.message);
      setCrosspointDestination(crosspointDestinationMode === 'sleep' ? DEFAULT_CROSSPOINT_DESTINATION : '');
      return;
    }
    setCrosspointDestination(destination);
    setUploading(true);
    setUploadProgress(null);
    localStorage.setItem('x4-crosspoint-host', crosspointHost);
    localStorage.setItem('x4-crosspoint-destination', destination);
    try {
      const device = await loadDevice();
      const details = await Promise.all(ids.map((id) => HOSTED
        ? Promise.resolve((hostedCatalog?.images || []).find((item) => item.id === id) || Promise.reject(new Error(`Unknown image ${id}`)))
        : get(`/api/images/${id}`)));
      const requiredBytes = details.reduce((sum, detail) => sum + (Number(detail.byte_size) || 0) + (64 * 1024), 0);
      if (device.storage.freeBytes !== null && requiredBytes > device.storage.freeBytes) {
        setNotice(`Upload blocked: ${bytesLabel(requiredBytes)} required, but only ${bytesLabel(device.storage.freeBytes)} is free on the X4.`);
        return;
      }
      for (let index = 0; index < ids.length; index += 1) {
        const id = ids[index];
        const detail = details[index];
        const sourceUrl = sourceUrlForSend(detail, id);
        if (!sourceUrl) throw new Error(`Original BMP for ${detail.filename} is missing from this snapshot.`);
        const source = await fetch(sourceUrl);
        if (!source.ok) throw new Error((await source.text()) || `Could not read ${detail.filename}.`);
        const blob = await source.blob();
        if (!(await blobIsBmp(blob))) throw new Error(`${detail.filename} did not load as a BMP. Refresh the page and try again.`);
        await uploadBlobToCrossPoint(crosspointHost, destination, detail.filename, blob, (received, totalBytes) => setUploadProgress({ index: index + 1, total: ids.length, filename: detail.filename, received, totalBytes }));
      }
      setNotice(`Sent ${ids.length} image${ids.length === 1 ? '' : 's'} to CrossPoint.`);
      clearSelection({ exit: true });
      await loadDevice();
    } catch (error) {
      setNotice(error.message);
    } finally {
      setUploading(false);
      setUploadProgress(null);
    }
  };
  const review = async (id, nextDecision) => {
    if (READ_ONLY_ARCHIVE) {
      setNotice(HOSTED ? 'Reviews stay on the local catalog. Publish again to update this snapshot.' : 'This public preview is read-only.');
      return;
    }
    try {
      await get(`/api/images/${id}/review`, { method: 'POST', body: JSON.stringify({ decision: nextDecision }) });
      setNotice(`Marked ${String(id).padStart(5, '0')} as ${nextDecision}.`);
      await Promise.all([loadImages(), inspect(id)]);
    } catch (error) { setNotice(error.message); }
  };
  const toggleSensitive = () => {
    setShowSensitive((current) => {
      const next = !current;
      localStorage.setItem('x4-show-sensitive', next ? '1' : '0');
      return next;
    });
  };
  const rebuild = async () => {
    if (READ_ONLY_ARCHIVE) {
      setNotice(HOSTED ? 'Views are rebuilt locally before publish.' : 'This public preview uses sample data only.');
      return;
    }
    if (rebuilding) return;
    setRebuilding(true);
    try { const result = await get('/api/views/rebuild', { method: 'POST' }); setNotice(`Rebuilt ${result.symlink_count} automatic/human tag symlinks.`); } catch (error) { setNotice(error.message); } finally { setRebuilding(false); }
  };
  const refreshDevice = async () => {
    try {
      await loadDevice();
      setNotice('');
    } catch (_) {
      // The device panel already displays the connection error and retry action.
    }
  };
  const loadMoreImages = () => {
    if (loadingMore || imageLoading || imageOffset >= imageTotal) return;
    loadImages({ append: true }).catch((error) => setNotice(error.message));
  };
  const imageResultLabel = imageLoading
    ? (images.length ? 'Updating…' : 'Loading…')
    : imageTotal > images.length
      ? `${images.length.toLocaleString()} of ${imageTotal.toLocaleString()} images`
      : `${imageTotal.toLocaleString()} images`;
  const resultScopeLabel = selectedTags.length ? selectedTags.map(prettyTag).join(' and ') : query || 'All pictures';

  return <>
    <header className="masthead">
      <a className="wordmark" href="/"><span>X4</span><strong>Catalog</strong></a>
      <nav className="site-nav" aria-label="Primary navigation">
        <a className={PAGE === 'browse' ? 'active' : ''} href={HOSTED ? '/browse' : '/'}>Browse</a>
        <a className={PAGE === 'device' ? 'active' : ''} href="/device">Device</a>
        <a className={PAGE === 'docs' ? 'active' : ''} href="/docs">Docs</a>
      </nav>
      <a className="nav-github" href={GITHUB_URL} aria-label="GitHub" title="GitHub" rel="noreferrer"><GitHubMark /></a>
      <div className="header-tools">
        {PUBLIC_DEMO && <span className="demo-chip">Demo</span>}
        {PAGE === 'browse' && !READ_ONLY_ARCHIVE && <button className="quiet-button" onClick={rebuild} disabled={rebuilding} aria-busy={rebuilding}>{rebuilding ? 'Refreshing…' : 'Refresh views'}</button>}
      </div>
    </header>
    <main>
      {PUBLIC_DEMO && <section className="demo-banner" role="status"><strong>DEMO</strong><span>Sample data · read-only</span></section>}
      {PAGE === 'home' ? <HomePage imageCount={hostedCatalog?.image_count} /> : PAGE === 'docs' ? <DocsPage /> : DEVICE_PAGE ? <>
        {!PUBLIC_DEMO && <DeviceHowTo />}
        <DeviceLibrary host={crosspointHost} setHost={setCrosspointHost} files={deviceFiles} books={deviceBooks} folders={deviceFolders} bookDirectory={bookDirectory} storage={deviceStorage} status={deviceStatus} loading={deviceLoading} uploading={bookUploading} uploadProgress={bookUploadProgress} error={deviceError} onRefresh={refreshDevice} onNavigateBooks={navigateBooks} onUploadBooks={uploadBooks} onMakeFolder={makeBookFolder} onRename={renameDeviceFile} onRenameBook={renameBook} onMoveBook={moveBook} onDelete={deleteDeviceFile} onDeleteBook={deleteBook} demo={PUBLIC_DEMO} />
        {notice && <section className="notice">{notice}</section>}
      </> : <>
        {SHOW_CLUSTERS && <div className="view-switch" role="tablist" aria-label="View"><button type="button" role="tab" aria-selected={mode === 'images'} className={mode === 'images' ? 'active' : ''} onClick={() => setMode('images')}>Pictures</button><button type="button" role="tab" aria-selected={mode === 'clusters'} className={mode === 'clusters' ? 'active' : ''} onClick={() => setMode('clusters')}>Clusters</button></div>}
        <FilterBar query={query} setQuery={setQuery} selectedTags={selectedTags} tags={tags} groups={HOSTED || PUBLIC_DEMO ? VISITOR_TAG_GROUPS : CURATOR_TAG_GROUPS} filtersOpen={filtersOpen} setFiltersOpen={setFiltersOpen} onToggleTag={toggleTag} onClearTags={() => setSelectedTags([])} onClearSearch={() => setQuery('')} tagSearch={tagSearch} setTagSearch={setTagSearch} tagGroup={tagGroup} setTagGroup={setTagGroup} showSensitive={showSensitive} onToggleSensitive={toggleSensitive} hosted={HOSTED} cluster={cluster} onClearCluster={() => setCluster(null)} />
        <div className="results-bar" role="status" aria-live="polite">
          <strong>{mode === 'images' ? imageResultLabel : `${clusters.length.toLocaleString()} clusters`}</strong>
          <span>{resultScopeLabel}</span>
          {mode === 'images' && <button type="button" className={`select-toggle ${selectionMode ? 'selection-active' : ''}`} onClick={toggleSelectionMode} aria-pressed={selectionMode} disabled={uploading || images.length === 0}>{selectionMode ? 'Done' : 'Select'}</button>}
        </div>
        <SendDock host={crosspointHost} setHost={setCrosspointHost} destination={crosspointDestination} setDestination={setCrosspointDestination} destinationMode={crosspointDestinationMode} onSelectSleep={selectSleepDestination} onSelectCustom={selectCustomDestination} onDestinationBlur={normalizeDestinationField} selectedCount={selectedIds.size} visibleCount={images.length} visibleSelectedCount={visibleSelectedCount} imageTotal={imageTotal} selectionMode={selectionMode} onToggleSelectionMode={toggleSelectionMode} onClear={clearSelection} onUpload={uploadSelected} onDownload={downloadSelected} onSelectVisible={selectVisible} onSelectAllMatches={selectAllMatches} selectionLoading={selectionLoading} uploading={uploading} progress={uploadProgress} demo={PUBLIC_DEMO} liveDevice={LIVE_DEVICE} filtered={Boolean(query || selectedTags.length || cluster)} />
        {notice && <section className="notice">{notice}</section>}
        {!SHOW_CLUSTERS || mode === 'images' ? <>
          <section ref={galleryRef} className={`gallery ${selectionMode ? 'selection-enabled' : ''}`} aria-label="Image results" aria-live="polite" aria-busy={imageLoading} onPointerDown={handleGalleryPointerDown} onKeyDown={handleGalleryKeyDown}>{images.length ? images.map((item) => <ImageCard key={item.id} item={item} onInspect={inspect} selected={selectedIds.has(item.id)} selectionMode={selectionMode} onSelect={selectImage} onKeyDown={handleImageKeyDown} consumeSuppressedClick={consumeSuppressedClick} showSensitive={showSensitive} visitor={HOSTED || PUBLIC_DEMO} />) : <div className="empty">{imageLoading ? 'Loading images…' : 'No images match these filters.'}</div>}</section>
          {marquee && <div className="marquee-selection" style={{ left: marquee.left, top: marquee.top, width: marquee.width, height: marquee.height }} aria-hidden="true" />}
          {images.length < imageTotal && <div className="load-more"><button type="button" onClick={loadMoreImages} disabled={loadingMore || imageLoading}>{loadingMore ? 'Loading…' : `Load more · ${(imageTotal - images.length).toLocaleString()} left`}</button><span>Showing {images.length.toLocaleString()} of {imageTotal.toLocaleString()}</span></div>}
        </> : <table className="cluster-list"><thead><tr><th>Cluster</th><th>Images</th><th>Outliers</th><th>Actions</th></tr></thead><tbody>{clusters.map((item) => <tr key={item.id}><td>{String(item.id).padStart(3,'0')}</td><td>{item.image_count}</td><td>{item.outlier_count}</td><td className="cluster-actions"><button type="button" onClick={() => { setCluster(item.id); setMode('images'); }}>Open</button><button type="button" onClick={() => selectCluster(item.id)} disabled={selectionLoading}>Select cluster</button></td></tr>)}</tbody></table>}
      </>}
    </main>
    <SiteFooter />
    <Inspector item={inspected} onClose={() => setInspected(null)} onReview={review} onQueue={queueFromInspector} onTag={filterFromInspector} queued={inspected ? selectedIds.has(inspected.id) : false} demo={READ_ONLY_ARCHIVE} liveDevice={LIVE_DEVICE} showSensitive={showSensitive} visitor={HOSTED || PUBLIC_DEMO} />
  </>;
}

createRoot(document.getElementById('root')).render(<App />);
