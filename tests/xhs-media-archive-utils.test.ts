import { describe, expect, it } from 'vitest';

import {
  buildByteRanges,
  checkMp4Structure,
  findCoverageGaps,
  hasCompleteCoverage,
  isCompleteMp4,
  parseContentRange,
  shouldArchiveMediaResponse,
} from '../src/xhs-media-archive-utils.js';

function box(type: string, payloadSize: number): Buffer {
  const buffer = Buffer.alloc(8 + payloadSize);
  buffer.writeUInt32BE(buffer.length, 0);
  buffer.write(type, 4, 4, 'ascii');
  return buffer;
}

describe('XHS media archive utilities', () => {
  it('builds byte ranges that cover non-even totals', () => {
    expect(buildByteRanges(10, 4)).toEqual([
      { start: 0, end: 3 },
      { start: 4, end: 7 },
      { start: 8, end: 9 },
    ]);
  });

  it('parses HTTP Content-Range headers', () => {
    expect(parseContentRange('bytes 1048576-2097151/4533594')).toEqual({
      start: 1048576,
      end: 2097151,
      total: 4533594,
    });
    expect(parseContentRange('bad')).toBeNull();
  });

  it('detects missing byte coverage gaps', () => {
    expect(findCoverageGaps([
      { start: 0, end: 4 },
      { start: 8, end: 9 },
    ], 10)).toEqual([[5, 7]]);
    expect(hasCompleteCoverage([
      { start: 5, end: 9 },
      { start: 0, end: 4 },
    ], 10)).toBe(true);
  });

  it('accepts complete top-level MP4 structures and rejects truncation', () => {
    const complete = Buffer.concat([box('ftyp', 4), box('moov', 6), box('mdat', 8)]);
    const truncated = complete.subarray(0, complete.length - 2);

    expect(isCompleteMp4(complete)).toBe(true);
    expect(isCompleteMp4(truncated)).toBe(false);
    expect(checkMp4Structure(truncated).completeStructure).toBe(false);
  });

  it('keeps XHS note media and rejects avatars/static resources', () => {
    expect(shouldArchiveMediaResponse({
      url: 'https://sns-webpic-qc.xhscdn.com/path/asset.webp',
      contentType: 'image/webp',
      status: 200,
    })).toBe(true);
    expect(shouldArchiveMediaResponse({
      url: 'https://sns-video-v4.xhscdn.com/stream/video.mp4',
      contentType: 'video/mp4',
      status: 206,
    })).toBe(true);
    expect(shouldArchiveMediaResponse({
      url: 'https://sns-avatar-qc.xhscdn.com/avatar/user.jpg',
      contentType: 'image/jpeg',
      status: 200,
    })).toBe(false);
    expect(shouldArchiveMediaResponse({
      url: 'https://fe-static.xhscdn.com/app.js',
      contentType: 'application/javascript',
      status: 200,
    })).toBe(false);
  });
});
