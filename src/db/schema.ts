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
