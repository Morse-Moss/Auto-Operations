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
import type { XhsRawSnapshotInput, XhsSearchNoteRow, XhsSearchRunInput } from '../xhs-types.js';
import type {
  CollectionRunRecord,
  HotWordContribution,
  NoteExportRow,
  RunReportData,
} from '../reporting/types.js';

interface CollectionRunDbRow {
  id: number;
  keyword: string;
  days: number;
  limit_hotwords: number;
  limit_notes: number;
  status: RunStatus;
  started_at: string;
  finished_at: string | null;
  error_stage: string | null;
  error_message: string | null;
}

interface HotWordContributionDbRow {
  hotWord: string;
  notes: number;
  topLikes: number | null;
  bestRank: number | null;
}

interface NoteExportDbRow {
  id: number;
  runId: number;
  sourceKeyword: string;
  hotWord: string;
  listRank: number | null;
  listPage: number | null;
  title: string;
  authorName: string | null;
  isVideo: number;
  publishedAt: string | null;
  likes: number | null;
  collects: number | null;
  comments: number | null;
  shares: number | null;
  estimatedReads: number | null;
  estimatedExposure: number | null;
  authorFollowers: number | null;
  authorNoteCount: number | null;
  readExposureRatioText: string | null;
  readFollowerRatioText: string | null;
  tagsJson: string;
  huitunNoteKey: string;
}

function mapCollectionRun(row: CollectionRunDbRow): CollectionRunRecord {
  return {
    id: row.id,
    keyword: row.keyword,
    days: row.days,
    limitHotwords: row.limit_hotwords,
    limitNotes: row.limit_notes,
    status: row.status,
    startedAt: row.started_at,
    finishedAt: row.finished_at,
    errorStage: row.error_stage,
    errorMessage: row.error_message,
  };
}

function mapHotWordContribution(row: HotWordContributionDbRow): HotWordContribution {
  return {
    hotWord: row.hotWord,
    notes: row.notes,
    topLikes: row.topLikes,
    bestRank: row.bestRank,
  };
}

function mapNoteExportRow(row: NoteExportDbRow): NoteExportRow {
  return {
    id: row.id,
    runId: row.runId,
    sourceKeyword: row.sourceKeyword,
    hotWord: row.hotWord,
    listRank: row.listRank,
    listPage: row.listPage,
    title: row.title,
    authorName: row.authorName,
    isVideo: row.isVideo,
    publishedAt: row.publishedAt,
    likes: row.likes,
    collects: row.collects,
    comments: row.comments,
    shares: row.shares,
    estimatedReads: row.estimatedReads,
    estimatedExposure: row.estimatedExposure,
    authorFollowers: row.authorFollowers,
    authorNoteCount: row.authorNoteCount,
    readExposureRatioText: row.readExposureRatioText,
    readFollowerRatioText: row.readFollowerRatioText,
    tagsJson: row.tagsJson,
    huitunNoteKey: row.huitunNoteKey,
  };
}

function ratio(numerator: number, denominator: number): number {
  if (denominator === 0) {
    return 0;
  }

  return numerator / denominator;
}

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

  findLatestFinishedRun(): CollectionRunRecord | null {
    const row = this.db
      .prepare(`
        select *
        from collection_runs
        where status != 'running'
        order by finished_at desc, id desc
        limit 1
      `)
      .get() as CollectionRunDbRow | undefined;

    return row ? mapCollectionRun(row) : null;
  }

  findRunById(runId: number): CollectionRunRecord | null {
    const row = this.db
      .prepare('select * from collection_runs where id = :runId')
      .get({ runId }) as CollectionRunDbRow | undefined;

    return row ? mapCollectionRun(row) : null;
  }

  getRunReportData(runId: number): RunReportData {
    const run = this.findRunById(runId);
    if (!run) {
      throw new Error(`Collection run not found: ${runId}`);
    }

    const totals = {
      hotWords: this.countHotWordsForRun(runId),
      hotWordSnapshots: this.countHotWordSnapshotsForRun(runId),
      notes: this.countNotesForRun(runId),
      detailedNotes: this.countDetailedNotesForRun(runId),
      rawSnapshots: this.countRawSnapshotsForRun(runId),
    };
    const likesCompletedRow = this.db
      .prepare(`
        select count(*) as count
        from notes
        where run_id = :runId
          and coalesce(list_likes, likes) is not null
      `)
      .get({ runId }) as { count: number };
    const hotWordContributions = (
      this.db
        .prepare(`
          select
            hot_word as hotWord,
            count(*) as notes,
            max(coalesce(list_likes, likes)) as topLikes,
            min(list_rank) as bestRank
          from notes
          where run_id = :runId
          group by hot_word
          order by notes desc, hotWord asc
        `)
        .all({ runId }) as unknown as HotWordContributionDbRow[]
    ).map(mapHotWordContribution);

    return {
      run,
      totals,
      detailCoverageRate: ratio(totals.detailedNotes, totals.notes),
      likesCompletenessRate: ratio(likesCompletedRow.count, totals.notes),
      rawSnapshotsByKind: this.countRawSnapshotsByKindForRun(runId),
      hotWordContributions,
    };
  }

  listNoteExportRows(runId: number): NoteExportRow[] {
    const rows = this.db
      .prepare(`
        with ranked_notes as (
          select
            id,
            run_id as runId,
            source_keyword as sourceKeyword,
            hot_word as hotWord,
            list_rank as listRank,
            list_page as listPage,
            title,
            author_name as authorName,
            is_video as isVideo,
            published_at as publishedAt,
            likes,
            collects,
            comments,
            shares,
            estimated_reads as estimatedReads,
            estimated_exposure as estimatedExposure,
            author_followers as authorFollowers,
            author_note_count as authorNoteCount,
            read_exposure_ratio_text as readExposureRatioText,
            read_follower_ratio_text as readFollowerRatioText,
            tags_json as tagsJson,
            huitun_note_key as huitunNoteKey,
            row_number() over (
              partition by huitun_note_key, coalesce(published_at, '')
              order by updated_record_at desc, id desc
            ) as identity_rank,
            list_likes
          from notes
          where run_id = :runId
        )
        select
          id,
          runId,
          sourceKeyword,
          hotWord,
          listRank,
          listPage,
          title,
          authorName,
          isVideo,
          publishedAt,
          likes,
          collects,
          comments,
          shares,
          estimatedReads,
          estimatedExposure,
          authorFollowers,
          authorNoteCount,
          readExposureRatioText,
          readFollowerRatioText,
          tagsJson,
          huitunNoteKey
        from ranked_notes
        where identity_rank = 1
        order by hotWord asc, (listRank is null) asc, listRank asc, (list_likes is null) asc, list_likes desc, id asc
      `)
      .all({ runId }) as unknown as NoteExportDbRow[];

    return rows.map(mapNoteExportRow);
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
          list_likes,
          updated_record_at
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
          :listLikes,
          current_timestamp
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

  createXhsSearchRun(input: XhsSearchRunInput): number {
    const result = this.db
      .prepare(`
        insert into xhs_search_runs (
          source,
          source_run_id,
          keyword,
          sorts_json,
          limit_per_sort,
          with_details,
          status
        ) values (
          :source,
          :sourceRunId,
          :keyword,
          :sortsJson,
          :limitPerSort,
          :withDetails,
          'running'
        )
      `)
      .run({
        source: input.source,
        sourceRunId: input.sourceRunId,
        keyword: input.keyword,
        sortsJson: JSON.stringify(input.sorts),
        limitPerSort: input.limitPerSort,
        withDetails: input.withDetails ? 1 : 0,
      });

    return Number(result.lastInsertRowid);
  }

  finishXhsSearchRun(runId: number, status: RunStatus, errorStage?: string, errorMessage?: string): void {
    this.db
      .prepare(`
        update xhs_search_runs
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

  upsertXhsSearchNotes(runId: number, rows: XhsSearchNoteRow[]): void {
    const upsert = this.db.prepare(`
      insert into xhs_search_notes (
        run_id,
        keyword,
        sort_key,
        sort_label,
        rank_index,
        feed_id,
        xsec_token,
        search_result_url,
        explore_url,
        title,
        author_name,
        author_profile_url,
        cover_url,
        published_at_text,
        metric_text,
        detail_text,
        detail_tags_json,
        detail_comment_count_text,
        detail_like_text,
        detail_collect_text,
        detail_share_text,
        note_type,
        cover_alt_text,
        raw_detail_text,
        source_topic_texts_json,
        source_comments_json,
        media_sources_json,
        analysis_source_text,
        raw_card_text,
        updated_record_at
      ) values (
        :runId,
        :keyword,
        :sortKey,
        :sortLabel,
        :rankIndex,
        :feedId,
        :xsecToken,
        :searchResultUrl,
        :exploreUrl,
        :title,
        :authorName,
        :authorProfileUrl,
        :coverUrl,
        :publishedAtText,
        :metricText,
        :detailText,
        :detailTagsJson,
        :detailCommentCountText,
        :detailLikeText,
        :detailCollectText,
        :detailShareText,
        :noteType,
        :coverAltText,
        :rawDetailText,
        :sourceTopicTextsJson,
        :sourceCommentsJson,
        :mediaSourcesJson,
        :analysisSourceText,
        :rawCardText,
        current_timestamp
      )
      on conflict(run_id, keyword, sort_key, feed_id) do update set
        sort_label = excluded.sort_label,
        rank_index = excluded.rank_index,
        xsec_token = excluded.xsec_token,
        search_result_url = excluded.search_result_url,
        explore_url = coalesce(excluded.explore_url, xhs_search_notes.explore_url),
        title = excluded.title,
        author_name = excluded.author_name,
        author_profile_url = excluded.author_profile_url,
        cover_url = excluded.cover_url,
        published_at_text = excluded.published_at_text,
        metric_text = excluded.metric_text,
        detail_text = coalesce(excluded.detail_text, xhs_search_notes.detail_text),
        detail_tags_json = case
          when excluded.detail_tags_json != '[]' then excluded.detail_tags_json
          else xhs_search_notes.detail_tags_json
        end,
        detail_comment_count_text = coalesce(excluded.detail_comment_count_text, xhs_search_notes.detail_comment_count_text),
        detail_like_text = coalesce(excluded.detail_like_text, xhs_search_notes.detail_like_text),
        detail_collect_text = coalesce(excluded.detail_collect_text, xhs_search_notes.detail_collect_text),
        detail_share_text = coalesce(excluded.detail_share_text, xhs_search_notes.detail_share_text),
        note_type = case
          when excluded.note_type != 'unknown' then excluded.note_type
          else xhs_search_notes.note_type
        end,
        cover_alt_text = coalesce(excluded.cover_alt_text, xhs_search_notes.cover_alt_text),
        raw_detail_text = coalesce(excluded.raw_detail_text, xhs_search_notes.raw_detail_text),
        source_topic_texts_json = case
          when excluded.source_topic_texts_json != '[]' then excluded.source_topic_texts_json
          else xhs_search_notes.source_topic_texts_json
        end,
        source_comments_json = case
          when excluded.source_comments_json != '[]' then excluded.source_comments_json
          else xhs_search_notes.source_comments_json
        end,
        media_sources_json = case
          when excluded.media_sources_json != '[]' then excluded.media_sources_json
          else xhs_search_notes.media_sources_json
        end,
        analysis_source_text = coalesce(excluded.analysis_source_text, xhs_search_notes.analysis_source_text),
        raw_card_text = excluded.raw_card_text,
        updated_record_at = current_timestamp
    `);

    this.db.exec('savepoint upsert_xhs_search_notes_batch');
    try {
      for (const row of rows) {
        upsert.run({
          runId,
          keyword: row.keyword,
          sortKey: row.sortKey,
          sortLabel: row.sortLabel,
          rankIndex: row.rankIndex,
          feedId: row.feedId,
          xsecToken: row.xsecToken,
          searchResultUrl: row.searchResultUrl,
          exploreUrl: row.exploreUrl,
          title: row.title,
          authorName: row.authorName,
          authorProfileUrl: row.authorProfileUrl,
          coverUrl: row.coverUrl,
          publishedAtText: row.publishedAtText,
          metricText: row.metricText,
          detailText: row.detailText,
          detailTagsJson: JSON.stringify(row.detailTags),
          detailCommentCountText: row.detailCommentCountText,
          detailLikeText: row.detailLikeText,
          detailCollectText: row.detailCollectText,
          detailShareText: row.detailShareText,
          noteType: row.noteType,
          coverAltText: row.coverAltText,
          rawDetailText: row.rawDetailText,
          sourceTopicTextsJson: JSON.stringify(row.sourceTopicTexts),
          sourceCommentsJson: JSON.stringify(row.sourceComments),
          mediaSourcesJson: JSON.stringify(row.mediaSources),
          analysisSourceText: row.analysisSourceText,
          rawCardText: row.rawCardText,
        });
      }
      this.db.exec('release upsert_xhs_search_notes_batch');
    } catch (error) {
      this.db.exec('rollback to upsert_xhs_search_notes_batch');
      this.db.exec('release upsert_xhs_search_notes_batch');
      throw error;
    }
  }

  insertXhsRawSnapshot(runId: number, snapshot: XhsRawSnapshotInput): void {
    this.db
      .prepare(`
        insert into xhs_raw_snapshots (
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

  listHotWordKeywordsForRun(runId: number, limit: number): string[] {
    const rows = this.db
      .prepare(`
        select word
        from hot_words
        where run_id = :runId
        order by rank_index asc, id asc
        limit :limit
      `)
      .all({ runId, limit }) as Array<{ word: string }>;

    return rows.map((row) => row.word);
  }
}
