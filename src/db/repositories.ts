import type { DatabaseSync } from 'node:sqlite';

import type {
  CollectionRunInput,
  HotWordRow,
  HotWordSnapshot,
  NoteDetail,
  NoteListRow,
  RawSnapshotInput,
  RunStatus,
} from '../types.js';

export class CollectorRepository {
  constructor(private readonly db: DatabaseSync) {}

  private countRows(tableName: 'hot_words' | 'notes', runId: number, where = ''): number {
    const row = this.db
      .prepare(`select count(*) as count from ${tableName} where run_id = :runId${where}`)
      .get({ runId }) as { count: number };
    return row.count;
  }

  countHotWordsForRun(runId: number): number {
    return this.countRows('hot_words', runId);
  }

  countNotesForRun(runId: number): number {
    return this.countRows('notes', runId);
  }

  countDetailedNotesForRun(runId: number): number {
    return this.countRows(
      'notes',
      runId,
      ` and (
        estimated_exposure is not null or
        shares is not null or
        author_followers is not null or
        author_note_count is not null or
        author_total_likes_collects is not null or
        read_exposure_ratio_text is not null or
        read_follower_ratio_text is not null
      )`,
    );
  }

  countHotWordSnapshotsForRun(runId: number): number {
    const row = this.db
      .prepare('select count(*) as count from hot_word_snapshots where run_id = :runId')
      .get({ runId }) as { count: number };
    return row.count;
  }

  countRawSnapshotsForRun(runId: number): number {
    const row = this.db
      .prepare('select count(*) as count from raw_snapshots where run_id = :runId')
      .get({ runId }) as { count: number };
    return row.count;
  }

  countRawSnapshotsByKindForRun(runId: number): Record<string, number> {
    const rows = this.db
      .prepare('select kind, count(*) as count from raw_snapshots where run_id = :runId group by kind order by kind')
      .all({ runId }) as Array<{ kind: string; count: number }>;
    return Object.fromEntries(rows.map((row) => [row.kind, row.count]));
  }

  createRun(input: CollectionRunInput): number {
    const result = this.db
      .prepare(`
        insert into collection_runs (keyword, days, limit_hotwords, limit_notes, status)
        values (:keyword, :days, :limitHotwords, :limitNotes, 'running')
      `)
      .run({
        keyword: input.keyword,
        days: input.days,
        limitHotwords: input.limitHotwords,
        limitNotes: input.limitNotes,
      });

    return Number(result.lastInsertRowid);
  }

  finishRun(runId: number, status: RunStatus, errorStage?: string, errorMessage?: string): void {
    this.db
      .prepare(`
        update collection_runs
        set status = :status,
            finished_at = current_timestamp,
            error_stage = :errorStage,
            error_message = :errorMessage
        where id = :runId
      `)
      .run({
        runId,
        status,
        errorStage: errorStage ?? null,
        errorMessage: errorMessage ?? null,
      });
  }

  insertHotWords(runId: number, rows: HotWordRow[]): void {
    const insert = this.db.prepare(`
      insert into hot_words (
        run_id,
        source_keyword,
        word,
        hot_value_text,
        hot_value_number,
        note_count,
        interaction_text,
        interaction_number,
        categories_json,
        rank_index
      ) values (
        :runId,
        :sourceKeyword,
        :word,
        :hotValueText,
        :hotValueNumber,
        :noteCount,
        :interactionText,
        :interactionNumber,
        :categoriesJson,
        :rankIndex
      )
    `);

    this.db.exec('savepoint insert_hot_words_batch');
    try {
      for (const row of rows) {
        insert.run({
          runId,
          sourceKeyword: row.sourceKeyword,
          word: row.word,
          hotValueText: row.hotValueText,
          hotValueNumber: row.hotValueNumber,
          noteCount: row.noteCount,
          interactionText: row.interactionText,
          interactionNumber: row.interactionNumber,
          categoriesJson: JSON.stringify(row.categories),
          rankIndex: row.rankIndex,
        });
      }
      this.db.exec('release insert_hot_words_batch');
    } catch (error) {
      this.db.exec('rollback to insert_hot_words_batch');
      this.db.exec('release insert_hot_words_batch');
      throw error;
    }
  }

  insertHotWordSnapshot(runId: number, snapshot: HotWordSnapshot): void {
    this.db
      .prepare(`
        insert into hot_word_snapshots (
          run_id,
          word,
          days,
          page_url,
          heat_text,
          related_notes_text,
          total_interactions_text,
          overview_json
        ) values (
          :runId,
          :word,
          :days,
          :pageUrl,
          :heatText,
          :relatedNotesText,
          :totalInteractionsText,
          :overviewJson
        )
      `)
      .run({
        runId,
        word: snapshot.word,
        days: snapshot.days,
        pageUrl: snapshot.pageUrl,
        heatText: snapshot.heatText,
        relatedNotesText: snapshot.relatedNotesText,
        totalInteractionsText: snapshot.totalInteractionsText,
        overviewJson: JSON.stringify(snapshot.overview),
      });
  }

  upsertNote(runId: number, sourceKeyword: string, row: NoteListRow, detail: NoteDetail | null): void {
    this.db
      .prepare(`
        insert into notes (
          run_id,
          source_keyword,
          hot_word,
          huitun_note_key,
          title,
          author_name,
          author_level,
          cover_url,
          is_video,
          video_duration,
          published_at,
          updated_at,
          tags_json,
          estimated_exposure,
          estimated_reads,
          likes,
          collects,
          comments,
          shares,
          author_followers,
          author_note_count,
          author_total_likes_collects,
          read_exposure_ratio_text,
          read_follower_ratio_text,
          list_rank,
          list_page,
          list_likes
        ) values (
          :runId,
          :sourceKeyword,
          :hotWord,
          :huitunNoteKey,
          :title,
          :authorName,
          :authorLevel,
          :coverUrl,
          :isVideo,
          :videoDuration,
          :publishedAt,
          :updatedAt,
          :tagsJson,
          :estimatedExposure,
          :estimatedReads,
          :likes,
          :collects,
          :comments,
          :shares,
          :authorFollowers,
          :authorNoteCount,
          :authorTotalLikesCollects,
          :readExposureRatioText,
          :readFollowerRatioText,
          :listRank,
          :listPage,
          :listLikes
        )
        on conflict(huitun_note_key, coalesce(published_at, '')) do update set
          run_id = excluded.run_id,
          source_keyword = excluded.source_keyword,
          hot_word = excluded.hot_word,
          title = excluded.title,
          author_name = excluded.author_name,
          author_level = excluded.author_level,
          cover_url = excluded.cover_url,
          is_video = excluded.is_video,
          video_duration = excluded.video_duration,
          updated_at = excluded.updated_at,
          tags_json = excluded.tags_json,
          estimated_exposure = coalesce(excluded.estimated_exposure, notes.estimated_exposure),
          estimated_reads = excluded.estimated_reads,
          likes = excluded.likes,
          collects = excluded.collects,
          comments = excluded.comments,
          shares = coalesce(excluded.shares, notes.shares),
          author_followers = coalesce(excluded.author_followers, notes.author_followers),
          author_note_count = coalesce(excluded.author_note_count, notes.author_note_count),
          author_total_likes_collects = coalesce(excluded.author_total_likes_collects, notes.author_total_likes_collects),
          read_exposure_ratio_text = coalesce(excluded.read_exposure_ratio_text, notes.read_exposure_ratio_text),
          read_follower_ratio_text = coalesce(excluded.read_follower_ratio_text, notes.read_follower_ratio_text),
          list_rank = coalesce(excluded.list_rank, notes.list_rank),
          list_page = coalesce(excluded.list_page, notes.list_page),
          list_likes = coalesce(excluded.list_likes, notes.list_likes),
          updated_record_at = current_timestamp
      `)
      .run({
        runId,
        sourceKeyword,
        hotWord: row.hotWord,
        huitunNoteKey: row.huitunNoteKey,
        title: row.title,
        authorName: row.authorName,
        authorLevel: row.authorLevel,
        coverUrl: row.coverUrl,
        isVideo: row.isVideo ? 1 : 0,
        videoDuration: row.videoDuration,
        publishedAt: row.publishedAt,
        updatedAt: row.updatedAt,
        tagsJson: JSON.stringify(row.tags),
        estimatedExposure: detail?.estimatedExposure ?? null,
        estimatedReads: detail?.estimatedReads ?? row.estimatedReads,
        likes: detail?.likes ?? row.likes,
        collects: detail?.collects ?? row.collects,
        comments: detail?.comments ?? row.comments,
        shares: detail?.shares ?? null,
        authorFollowers: detail?.authorFollowers ?? null,
        authorNoteCount: detail?.authorNoteCount ?? null,
        authorTotalLikesCollects: detail?.authorTotalLikesCollects ?? null,
        readExposureRatioText: detail?.readExposureRatioText ?? null,
        readFollowerRatioText: detail?.readFollowerRatioText ?? null,
        listRank: row.listRank ?? null,
        listPage: row.listPage ?? null,
        listLikes: row.likes,
      });
  }

  insertRawSnapshot(runId: number, snapshot: RawSnapshotInput): void {
    this.db
      .prepare(`
        insert into raw_snapshots (
          run_id,
          kind,
          object_key,
          page_url,
          text_content,
          html_content
        ) values (
          :runId,
          :kind,
          :objectKey,
          :pageUrl,
          :textContent,
          :htmlContent
        )
      `)
      .run({
        runId,
        kind: snapshot.kind,
        objectKey: snapshot.objectKey,
        pageUrl: snapshot.pageUrl,
        textContent: snapshot.textContent,
        htmlContent: snapshot.htmlContent,
      });
  }
}
