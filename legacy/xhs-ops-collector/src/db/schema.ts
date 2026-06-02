import type { DatabaseSync } from 'node:sqlite';

function ensureColumn(db: DatabaseSync, tableName: string, columnName: string, definition: string): void {
  const columns = db.prepare(`pragma table_info(${tableName})`).all() as Array<{ name: string }>;
  if (!columns.some((column) => column.name === columnName)) {
    db.exec(`alter table ${tableName} add column ${columnName} ${definition}`);
  }
}

export function initializeSchema(db: DatabaseSync): void {
  db.exec(`
    create table if not exists collection_runs (
      id integer primary key autoincrement,
      keyword text not null,
      days integer not null,
      limit_hotwords integer not null,
      limit_notes integer not null,
      status text not null,
      started_at text not null default current_timestamp,
      finished_at text,
      error_stage text,
      error_message text
    );

    create table if not exists hot_words (
      id integer primary key autoincrement,
      run_id integer not null references collection_runs(id) on delete cascade,
      source_keyword text not null,
      word text not null,
      hot_value_text text,
      hot_value_number real,
      note_count integer,
      interaction_text text,
      interaction_number real,
      categories_json text not null,
      rank_index integer not null
    );

    create table if not exists hot_word_snapshots (
      id integer primary key autoincrement,
      run_id integer not null references collection_runs(id) on delete cascade,
      word text not null,
      days integer not null,
      page_url text not null,
      heat_text text,
      related_notes_text text,
      total_interactions_text text,
      overview_json text not null,
      captured_at text not null default current_timestamp
    );

    create table if not exists notes (
      id integer primary key autoincrement,
      run_id integer not null references collection_runs(id) on delete cascade,
      source_keyword text not null,
      hot_word text not null,
      huitun_note_key text not null,
      title text not null,
      author_name text,
      author_level text,
      cover_url text,
      is_video integer not null,
      video_duration text,
      published_at text,
      updated_at text,
      tags_json text not null,
      estimated_exposure integer,
      estimated_reads integer,
      likes integer,
      collects integer,
      comments integer,
      shares integer,
      author_followers integer,
      author_note_count integer,
      author_total_likes_collects integer,
      read_exposure_ratio_text text,
      read_follower_ratio_text text,
      list_rank integer,
      list_page integer,
      list_likes integer,
      created_at text not null default current_timestamp,
      updated_record_at text not null default current_timestamp,
      unique(huitun_note_key, published_at)
    );

    create table if not exists raw_snapshots (
      id integer primary key autoincrement,
      run_id integer not null references collection_runs(id) on delete cascade,
      kind text not null,
      object_key text not null,
      page_url text not null,
      text_content text not null,
      html_content text,
      captured_at text not null default current_timestamp
    );

    create table if not exists xhs_search_runs (
      id integer primary key autoincrement,
      source text not null,
      source_run_id integer,
      keyword text not null,
      sorts_json text not null,
      limit_per_sort integer not null,
      with_details integer not null,
      status text not null,
      started_at text not null default current_timestamp,
      finished_at text,
      error_stage text,
      error_message text
    );

    create table if not exists xhs_search_notes (
      id integer primary key autoincrement,
      run_id integer not null references xhs_search_runs(id) on delete cascade,
      keyword text not null,
      sort_key text not null,
      sort_label text not null,
      rank_index integer not null,
      feed_id text not null,
      xsec_token text,
      search_result_url text not null,
      explore_url text,
      title text not null,
      author_name text,
      author_profile_url text,
      cover_url text,
      published_at_text text,
      metric_text text,
      detail_text text,
      detail_tags_json text not null,
      detail_comment_count_text text,
      detail_like_text text,
      detail_collect_text text,
      detail_share_text text,
      note_type text not null default 'unknown',
      cover_alt_text text,
      raw_detail_text text,
      source_topic_texts_json text not null default '[]',
      source_comments_json text not null default '[]',
      media_sources_json text not null default '[]',
      analysis_source_text text,
      raw_card_text text not null,
      collected_at text not null default current_timestamp,
      updated_record_at text not null default current_timestamp,
      unique(run_id, keyword, sort_key, feed_id)
    );

    create table if not exists xhs_raw_snapshots (
      id integer primary key autoincrement,
      run_id integer not null references xhs_search_runs(id) on delete cascade,
      kind text not null,
      object_key text not null,
      page_url text not null,
      text_content text not null,
      html_content text,
      captured_at text not null default current_timestamp
    );

    create index if not exists idx_hot_words_run_id on hot_words(run_id);
    create index if not exists idx_hot_word_snapshots_run_id on hot_word_snapshots(run_id);
    create index if not exists idx_notes_run_id on notes(run_id);
    create index if not exists idx_notes_huitun_note_key on notes(huitun_note_key);
    create index if not exists idx_notes_run_note_key on notes(run_id, huitun_note_key);
    create index if not exists idx_raw_snapshots_run_id on raw_snapshots(run_id);
    create index if not exists idx_raw_snapshots_object_key on raw_snapshots(object_key);
  `);

  ensureColumn(db, 'collection_runs', 'error_stage', 'text');
  ensureColumn(db, 'collection_runs', 'error_message', 'text');
  ensureColumn(db, 'notes', 'estimated_exposure', 'integer');
  ensureColumn(db, 'notes', 'shares', 'integer');
  ensureColumn(db, 'notes', 'author_followers', 'integer');
  ensureColumn(db, 'notes', 'author_note_count', 'integer');
  ensureColumn(db, 'notes', 'author_total_likes_collects', 'integer');
  ensureColumn(db, 'notes', 'read_exposure_ratio_text', 'text');
  ensureColumn(db, 'notes', 'read_follower_ratio_text', 'text');
  ensureColumn(db, 'notes', 'list_rank', 'integer');
  ensureColumn(db, 'notes', 'list_page', 'integer');
  ensureColumn(db, 'notes', 'list_likes', 'integer');
  ensureColumn(db, 'notes', 'updated_record_at', 'text');
  ensureColumn(db, 'xhs_search_runs', 'source_run_id', 'integer');
  ensureColumn(db, 'xhs_search_runs', 'finished_at', 'text');
  ensureColumn(db, 'xhs_search_runs', 'error_stage', 'text');
  ensureColumn(db, 'xhs_search_runs', 'error_message', 'text');
  ensureColumn(db, 'xhs_search_notes', 'run_id', 'integer');
  ensureColumn(db, 'xhs_search_notes', 'feed_id', 'text');
  ensureColumn(db, 'xhs_search_notes', 'explore_url', 'text');
  ensureColumn(db, 'xhs_search_notes', 'detail_text', 'text');
  ensureColumn(db, 'xhs_search_notes', 'detail_tags_json', 'text');
  ensureColumn(db, 'xhs_search_notes', 'detail_comment_count_text', 'text');
  ensureColumn(db, 'xhs_search_notes', 'detail_like_text', 'text');
  ensureColumn(db, 'xhs_search_notes', 'detail_collect_text', 'text');
  ensureColumn(db, 'xhs_search_notes', 'detail_share_text', 'text');
  ensureColumn(db, 'xhs_search_notes', 'note_type', "text not null default 'unknown'");
  ensureColumn(db, 'xhs_search_notes', 'cover_alt_text', 'text');
  ensureColumn(db, 'xhs_search_notes', 'raw_detail_text', 'text');
  ensureColumn(db, 'xhs_search_notes', 'source_topic_texts_json', "text not null default '[]'");
  ensureColumn(db, 'xhs_search_notes', 'source_comments_json', "text not null default '[]'");
  ensureColumn(db, 'xhs_search_notes', 'media_sources_json', "text not null default '[]'");
  ensureColumn(db, 'xhs_search_notes', 'analysis_source_text', 'text');
  ensureColumn(db, 'xhs_search_notes', 'updated_record_at', 'text');
  ensureColumn(db, 'xhs_raw_snapshots', 'run_id', 'integer');
  ensureColumn(db, 'xhs_raw_snapshots', 'html_content', 'text');
  db.exec("update xhs_search_notes set detail_tags_json = '[]' where detail_tags_json is null");
  db.exec("update xhs_search_notes set note_type = 'unknown' where note_type is null or note_type = ''");
  db.exec("update xhs_search_notes set source_topic_texts_json = '[]' where source_topic_texts_json is null");
  db.exec("update xhs_search_notes set source_comments_json = '[]' where source_comments_json is null");
  db.exec("update xhs_search_notes set media_sources_json = '[]' where media_sources_json is null");
  db.exec('update xhs_search_notes set updated_record_at = current_timestamp where updated_record_at is null');

  const xhsSearchNoteColumns = db.prepare('pragma table_info(xhs_search_notes)').all() as Array<{
    name: string;
    notnull: number;
  }>;
  if (xhsSearchNoteColumns.some((column) => column.name === 'feed_id' && column.notnull === 0)) {
    db.exec("update xhs_search_notes set feed_id = null where feed_id = ''");
  }

  db.exec(`
    with feed_id_sources as (
      select
        id,
        case
          when instr(search_result_url, '/search_result/') > 0 then
            substr(search_result_url, instr(search_result_url, '/search_result/') + length('/search_result/'))
          when explore_url is not null and instr(explore_url, '/explore/') > 0 then
            substr(explore_url, instr(explore_url, '/explore/') + length('/explore/'))
        end as feed_id_tail
      from xhs_search_notes
      where feed_id is null or feed_id = ''
    ),
    feed_id_candidates as (
      select
        id,
        case
          when feed_id_tail is null or feed_id_tail = '' then null
          when instr(feed_id_tail, '?') > 0
            and (instr(feed_id_tail, '/') = 0 or instr(feed_id_tail, '?') < instr(feed_id_tail, '/')) then
            substr(feed_id_tail, 1, instr(feed_id_tail, '?') - 1)
          when instr(feed_id_tail, '/') > 0 then
            substr(feed_id_tail, 1, instr(feed_id_tail, '/') - 1)
          else feed_id_tail
        end as feed_id_candidate
      from feed_id_sources
    )
    update xhs_search_notes
    set feed_id = (
      select feed_id_candidate
      from feed_id_candidates
      where feed_id_candidates.id = xhs_search_notes.id
    )
    where id in (
      select id
      from feed_id_candidates
      where feed_id_candidate is not null and feed_id_candidate != ''
    );

    delete from xhs_search_notes
    where feed_id is not null
      and feed_id != ''
      and id not in (
        select id
        from (
          select
            id,
            row_number() over (
              partition by run_id, keyword, sort_key, feed_id
              order by updated_record_at desc, id desc
            ) as identity_rank
          from xhs_search_notes
          where feed_id is not null and feed_id != ''
        )
        where identity_rank = 1
      );

    create unique index if not exists idx_xhs_search_notes_identity on xhs_search_notes(run_id, keyword, sort_key, feed_id);
  `);
  db.exec(`
    create index if not exists idx_xhs_search_runs_source_run_id on xhs_search_runs(source_run_id);
    create index if not exists idx_xhs_search_notes_run_id on xhs_search_notes(run_id);
    create index if not exists idx_xhs_search_notes_feed_id on xhs_search_notes(feed_id);
    create index if not exists idx_xhs_raw_snapshots_run_id on xhs_raw_snapshots(run_id);
  `);
  db.exec('update notes set updated_record_at = current_timestamp where updated_record_at is null');
  db.exec(`
    delete from notes
    where id not in (
      select id
      from (
        select
          id,
          row_number() over (
            partition by huitun_note_key, coalesce(published_at, '')
            order by updated_record_at desc, id desc
          ) as identity_rank
        from notes
      )
      where identity_rank = 1
    );

    create unique index if not exists idx_notes_stable_identity on notes(huitun_note_key, coalesce(published_at, ''));
  `);
}
