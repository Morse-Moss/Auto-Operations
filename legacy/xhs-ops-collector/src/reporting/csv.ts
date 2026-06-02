import type { NoteExportRow } from './types.js';

export const NOTE_EXPORT_HEADERS = [
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
] as const;

type CsvCell = string | number | boolean | null;
type NoteExportHeader = (typeof NOTE_EXPORT_HEADERS)[number];

function parseTags(tagsJson: string): string {
  try {
    const parsed = JSON.parse(tagsJson) as unknown;
    if (Array.isArray(parsed)) {
      return parsed.map((tag) => String(tag)).join('|');
    }
  } catch {
    return tagsJson;
  }

  return tagsJson;
}

function formatCell(value: CsvCell): string {
  if (value === null) {
    return '';
  }

  const text = String(value);
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

function mapRow(row: NoteExportRow): Record<NoteExportHeader, CsvCell> {
  return {
    run_id: row.runId,
    source_keyword: row.sourceKeyword,
    hot_word: row.hotWord,
    list_rank: row.listRank,
    list_page: row.listPage,
    title: row.title,
    author_name: row.authorName,
    is_video: row.isVideo === 1,
    published_at: row.publishedAt,
    likes: row.likes,
    collects: row.collects,
    comments: row.comments,
    shares: row.shares,
    estimated_reads: row.estimatedReads,
    estimated_exposure: row.estimatedExposure,
    author_followers: row.authorFollowers,
    author_note_count: row.authorNoteCount,
    read_exposure_ratio_text: row.readExposureRatioText,
    read_follower_ratio_text: row.readFollowerRatioText,
    tags: parseTags(row.tagsJson),
    huitun_note_key: row.huitunNoteKey,
  };
}

export function serializeNoteExportRows(rows: NoteExportRow[]): string {
  const lines = [
    NOTE_EXPORT_HEADERS.join(','),
    ...rows.map((row) => {
      const mapped = mapRow(row);
      return NOTE_EXPORT_HEADERS.map((header) => formatCell(mapped[header])).join(',');
    }),
  ];

  return `${lines.join('\n')}\n`;
}
