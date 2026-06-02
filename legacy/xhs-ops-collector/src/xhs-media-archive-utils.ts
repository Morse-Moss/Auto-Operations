import { relative, sep } from 'node:path';

export interface ByteRange {
  start: number;
  end: number;
}

export interface ParsedContentRange extends ByteRange {
  total: number;
}

export interface Mp4Box {
  offset: number;
  type: string;
  size: number;
  valid: boolean;
}

export interface Mp4StructureCheck {
  bytes: number;
  parsedBytes: number;
  completeStructure: boolean;
  hasFtyp: boolean;
  hasMoov: boolean;
  hasMdat: boolean;
  boxes: Mp4Box[];
}

export function sanitizePathSegment(value: string): string {
  return value.replace(/[<>:"/\\|?*\x00-\x1F]/g, '_').slice(0, 80);
}

export function relativePosixPath(from: string, to: string): string {
  return relative(from, to).split(sep).join('/');
}

export function parseJsonArray<T>(value: string | null): T[] {
  if (value === null || value === '') {
    return [];
  }

  try {
    const parsed: unknown = JSON.parse(value);
    return Array.isArray(parsed) ? parsed as T[] : [];
  } catch {
    return [];
  }
}

export function csvCell(value: unknown): string {
  const text = value === null || value === undefined ? '' : String(value);
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function parseContentRange(value: string | null | undefined): ParsedContentRange | null {
  const match = /^bytes\s+(\d+)-(\d+)\/(\d+)$/i.exec(value ?? '');
  if (match === null) {
    return null;
  }

  return {
    start: Number(match[1]),
    end: Number(match[2]),
    total: Number(match[3]),
  };
}

export function buildByteRanges(totalBytes: number, blockSize: number): ByteRange[] {
  if (!Number.isInteger(totalBytes) || totalBytes <= 0 || !Number.isInteger(blockSize) || blockSize <= 0) {
    return [];
  }

  const ranges: ByteRange[] = [];
  for (let start = 0; start < totalBytes; start += blockSize) {
    ranges.push({ start, end: Math.min(totalBytes - 1, start + blockSize - 1) });
  }
  return ranges;
}

export function findCoverageGaps(chunks: ByteRange[], totalBytes: number): Array<[number, number]> {
  if (totalBytes <= 0) {
    return [];
  }

  const sorted = [...chunks].sort((a, b) => a.start - b.start);
  const gaps: Array<[number, number]> = [];
  let expectedStart = 0;

  for (const chunk of sorted) {
    if (chunk.start > expectedStart) {
      gaps.push([expectedStart, chunk.start - 1]);
    }
    expectedStart = Math.max(expectedStart, chunk.end + 1);
  }

  if (expectedStart < totalBytes) {
    gaps.push([expectedStart, totalBytes - 1]);
  }

  return gaps;
}

export function hasCompleteCoverage(chunks: ByteRange[], totalBytes: number): boolean {
  return totalBytes > 0 && findCoverageGaps(chunks, totalBytes).length === 0;
}

export function detectMediaKind(url: string, contentType: string): 'image' | 'video' | null {
  const normalizedContentType = contentType.toLowerCase();
  const normalizedUrl = url.toLowerCase();
  if (normalizedContentType.startsWith('video/') || normalizedUrl.includes('.mp4') || normalizedUrl.includes('.m3u8') || normalizedUrl.includes('sns-video')) {
    return 'video';
  }
  if (normalizedContentType.startsWith('image/') && /sns-webpic|sns-img|ci\.xiaohongshu\.com/.test(normalizedUrl)) {
    return 'image';
  }
  return null;
}

export function shouldArchiveMediaResponse(params: { url: string; contentType: string; status: number }): boolean {
  const normalizedUrl = params.url.toLowerCase();
  const normalizedContentType = params.contentType.toLowerCase();
  if (!/sns-webpic|sns-img|sns-video|ci\.xiaohongshu\.com/.test(normalizedUrl)) {
    return false;
  }
  if (/sns-avatar|\/avatar\//.test(normalizedUrl)) {
    return false;
  }
  if (params.status >= 400) {
    return false;
  }

  const kind = detectMediaKind(params.url, params.contentType);
  if (kind === 'image') {
    return normalizedContentType.startsWith('image/');
  }
  return kind === 'video' && (normalizedContentType.startsWith('video/') || /\.mp4|\.m3u8/.test(normalizedUrl));
}

export function extensionFromContentType(contentType: string): string {
  const normalized = contentType.toLowerCase();
  if (normalized.includes('image/webp')) return '.webp';
  if (normalized.includes('image/jpeg')) return '.jpg';
  if (normalized.includes('image/png')) return '.png';
  if (normalized.includes('image/avif')) return '.avif';
  if (normalized.includes('video/mp4')) return '.mp4';
  if (normalized.includes('mpegurl') || normalized.includes('m3u8')) return '.m3u8';
  return '';
}

export function extensionFromUrl(url: string): string {
  const pathname = new URL(url).pathname.toLowerCase();
  if (pathname.includes('.mp4')) return '.mp4';
  if (pathname.includes('.m3u8')) return '.m3u8';
  if (pathname.includes('.webp')) return '.webp';
  if (pathname.includes('.jpg') || pathname.includes('.jpeg')) return '.jpg';
  if (pathname.includes('.png')) return '.png';
  if (pathname.includes('.avif')) return '.avif';
  return '';
}

export function checkMp4Structure(buffer: Buffer): Mp4StructureCheck {
  const boxes: Mp4Box[] = [];
  let offset = 0;

  while (offset + 8 <= buffer.length) {
    let size = buffer.readUInt32BE(offset);
    const type = buffer.toString('ascii', offset + 4, offset + 8);
    let headerSize = 8;

    if (size === 1 && offset + 16 <= buffer.length) {
      const high = buffer.readUInt32BE(offset + 8);
      const low = buffer.readUInt32BE(offset + 12);
      size = high * 2 ** 32 + low;
      headerSize = 16;
    } else if (size === 0) {
      size = buffer.length - offset;
    }

    if (size < headerSize || offset + size > buffer.length) {
      boxes.push({ offset, type, size, valid: false });
      break;
    }

    boxes.push({ offset, type, size, valid: true });
    offset += size;
  }

  const completeStructure = offset === buffer.length && boxes.every((box) => box.valid);
  const types = new Set(boxes.filter((box) => box.valid).map((box) => box.type));
  return {
    bytes: buffer.length,
    parsedBytes: offset,
    completeStructure,
    hasFtyp: types.has('ftyp'),
    hasMoov: types.has('moov'),
    hasMdat: types.has('mdat'),
    boxes,
  };
}

export function isCompleteMp4(buffer: Buffer): boolean {
  const check = checkMp4Structure(buffer);
  return check.completeStructure && check.hasFtyp && check.hasMoov && check.hasMdat;
}
