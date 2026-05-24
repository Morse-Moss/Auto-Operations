import { describe, expect, it } from 'vitest';

import { NOTE_EXPORT_HEADERS, serializeNoteExportRows } from '../src/reporting/csv.js';
import type { NoteExportRow } from '../src/reporting/types.js';

const baseRow: NoteExportRow = {
  id: 1,
  runId: 9,
  sourceKeyword: '护肤',
  hotWord: '早C晚A',
  listRank: 1,
  listPage: 1,
  title: '标题,含逗号',
  authorName: '作者"A',
  isVideo: 0,
  publishedAt: '2026-05-01',
  likes: 120,
  collects: 30,
  comments: 4,
  shares: 2,
  estimatedReads: 1000,
  estimatedExposure: 5000,
  authorFollowers: 20000,
  authorNoteCount: 88,
  readExposureRatioText: '20%',
  readFollowerRatioText: '5%',
  tagsJson: JSON.stringify(['精华', '抗老']),
  huitunNoteKey: 'note-1',
};

describe('serializeNoteExportRows', () => {
  it('writes the fixed CSV header', () => {
    expect(NOTE_EXPORT_HEADERS).toEqual([
      'run_id',
      'source_keyword',
      'hot_word',
      'list_rank',
      'list_page',
      'title',
      'author_name',
      'is_video',
      'published_at',
      'likes',
      'collects',
      'comments',
      'shares',
      'estimated_reads',
      'estimated_exposure',
      'author_followers',
      'author_note_count',
      'read_exposure_ratio_text',
      'read_follower_ratio_text',
      'tags',
      'huitun_note_key',
    ]);
  });

  it('serializes rows with CSV escaping and parsed tags', () => {
    expect(serializeNoteExportRows([baseRow])).toBe(
      'run_id,source_keyword,hot_word,list_rank,list_page,title,author_name,is_video,published_at,likes,collects,comments,shares,estimated_reads,estimated_exposure,author_followers,author_note_count,read_exposure_ratio_text,read_follower_ratio_text,tags,huitun_note_key\n' +
        '9,护肤,早C晚A,1,1,"标题,含逗号","作者""A",false,2026-05-01,120,30,4,2,1000,5000,20000,88,20%,5%,精华|抗老,note-1\n',
    );
  });

  it('serializes null values as empty cells and preserves invalid tags text', () => {
    const csv = serializeNoteExportRows([
      {
        ...baseRow,
        listRank: null,
        authorName: null,
        likes: null,
        tagsJson: 'not-json',
      },
    ]);

    expect(csv).toContain('9,护肤,早C晚A,,1,"标题,含逗号",,false,2026-05-01,');
    expect(csv).toContain('not-json,note-1\n');
  });

  it('preserves valid non-array tags text', () => {
    expect(serializeNoteExportRows([{ ...baseRow, tagsJson: '{"tag":"精华"}' }])).toContain('"{""tag"":""精华""}",note-1\n');
  });

  it('escapes newlines inside cells', () => {
    expect(serializeNoteExportRows([{ ...baseRow, title: '第一行\n第二行' }])).toContain('"第一行\n第二行"');
  });

  it('escapes carriage returns inside cells', () => {
    expect(serializeNoteExportRows([{ ...baseRow, title: '第一行\r第二行' }])).toContain('"第一行\r第二行"');
  });
});
