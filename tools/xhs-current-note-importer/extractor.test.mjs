import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test } from "node:test";
import { Script, createContext } from "node:vm";

function loadExtractor() {
  const source = readFileSync(join(import.meta.dirname, "extractor.js"), "utf8");
  const context = createContext({ globalThis: {} });
  new Script(source).runInContext(context);
  return context.globalThis.XhsCurrentNoteImporter;
}

function sampleState() {
  const noteId = "6a45e1250000000022014470";
  const keys = [
    "notes_pre_post/1040g3k03223tv026na2g5nv0648g80tctrfrc9o",
    "notes_pre_post/1040g3k03223tv026na005nv0648g80tc8psra6o",
    "notes_pre_post/1040g3k03223tv026na0g5nv0648g80tc7qmsgn0",
    "notes_pre_post/1040g3k03223tv026na105nv0648g80tcfj7g5v0",
    "notes_pre_post/1040g3k03223tv026na1g5nv0648g80tc3peehd8",
    "notes_pre_post/1040g3k03223tv026na205nv0648g80tcg1smcto",
  ];
  return {
    note: {
      noteDetailMap: {
        [noteId]: {
          note: {
            noteId,
            type: "normal",
            title: "6-image sample note",
            desc: "Body copied from state.",
            user: { nickname: "sample author", userId: "author-1" },
            tagList: [{ name: "tag-a" }, { name: "tag-b" }],
            imageList: keys.map((key) => ({
              urlDefault: `https://sns-webpic-qc.xhscdn.com/202407/${key}!nd_whgt34_webp_3`,
            })),
          },
        },
      },
    },
  };
}

test("extractCurrentNote maps the sample note's six image URLs", () => {
  const extractor = loadExtractor();
  const payload = extractor.extractCurrentNote({
    locationLike: {
      href: "https://www.xiaohongshu.com/explore/6a45e1250000000022014470?xsec_source=pc_feed",
      pathname: "/explore/6a45e1250000000022014470",
    },
    documentLike: {
      title: "fallback",
      images: [],
      querySelector: () => null,
      querySelectorAll: () => [],
    },
    initialState: sampleState(),
  });

  assert.equal(payload.note_id, "6a45e1250000000022014470");
  assert.equal(payload.title, "6-image sample note");
  assert.equal(payload.content, "Body copied from state.");
  assert.equal(JSON.stringify(payload.tags), JSON.stringify(["tag-a", "tag-b"]));
  assert.equal(payload.image_urls.length, 6);
  assert.match(payload.image_urls[0], /1040g3k03223tv026na2g5nv0648g80tctrfrc9o/);
  assert.equal(payload.raw.extracted_from, "current_page");
});

test("imageUrlsFromDom dedupes carousel clones by XHS media key", () => {
  const extractor = loadExtractor();
  const keys = [
    "notes_pre_post/1040g3k03223tv026na2g5nv0648g80tctrfrc9o",
    "notes_pre_post/1040g3k03223tv026na005nv0648g80tc8psra6o",
    "notes_pre_post/1040g3k03223tv026na0g5nv0648g80tc7qmsgn0",
    "notes_pre_post/1040g3k03223tv026na105nv0648g80tcfj7g5v0",
    "notes_pre_post/1040g3k03223tv026na1g5nv0648g80tc3peehd8",
    "notes_pre_post/1040g3k03223tv026na205nv0648g80tcg1smcto",
  ];
  const urls = [
    `https://sns-webpic-qc.xhscdn.com/202607071002/a/${keys[0]}!nd_dft_wlteh_webp_3`,
    `https://sns-webpic-qc.xhscdn.com/202607071002/b/${keys[1]}!nd_dft_wlteh_webp_3`,
    `http://sns-webpic-qc.xhscdn.com/202607071002/b/${keys[1]}!nd_dft_wlteh_webp_3`,
    `https://sns-webpic-qc.xhscdn.com/202607071002/c/${keys[2]}!nd_dft_wlteh_webp_3`,
    `https://sns-webpic-qc.xhscdn.com/202607071002/d/${keys[3]}!nd_dft_wlteh_webp_3`,
    `https://sns-webpic-qc.xhscdn.com/202607071002/e/${keys[4]}!nd_dft_wlteh_webp_3`,
    `https://sns-webpic-qc.xhscdn.com/202607071002/f/${keys[5]}!nd_dft_wlteh_webp_3`,
    `https://sns-webpic-qc.xhscdn.com/202607071002/a/${keys[0]}!nd_dft_wlteh_webp_3`,
  ];

  const imageUrls = extractor.imageUrlsFromDom({
    images: urls.map((src) => ({ src, currentSrc: src })),
  });

  assert.equal(imageUrls.length, 6);
  for (const key of keys) {
    assert.equal(imageUrls.filter((url) => url.includes(key)).length, 1);
  }
});

test("normal image notes do not save blob video URLs from the page shell", () => {
  const extractor = loadExtractor();
  const payload = extractor.extractCurrentNote({
    locationLike: {
      href: "https://www.xiaohongshu.com/explore/6a45e1250000000022014470",
      pathname: "/explore/6a45e1250000000022014470",
    },
    documentLike: {
      title: "fallback",
      images: [{ src: "https://sns-webpic-qc.xhscdn.com/a/notes_pre_post/key!webp", currentSrc: "" }],
      querySelector: (selector) => {
        if (selector === "video") return { src: "blob:https://www.xiaohongshu.com/video", currentSrc: "" };
        return null;
      },
      querySelectorAll: () => [],
    },
    initialState: {
      note: {
        noteDetailMap: {
          "6a45e1250000000022014470": {
            note: {
              noteId: "6a45e1250000000022014470",
              type: "normal",
              title: "image note",
              imageList: [],
            },
          },
        },
      },
    },
  });

  assert.equal(payload.video_url, "");
});

test("visibleComments strips query tokens from user ids before submit", () => {
  const extractor = loadExtractor();
  const comments = extractor.visibleComments({
    querySelectorAll: () => [
      {
        id: "comment-1",
        textContent: "多少钱",
        querySelector: (selector) => {
          if (selector === ".content") return { textContent: "多少钱" };
          if (selector === "a[href*='/user/profile/']") {
            return {
              textContent: "user",
              getAttribute: () =>
                "/user/profile/5efb4b8b00000000010068f6?channel_type=web_note_detail_r10&xsec_token=secret",
            };
          }
          return null;
        },
      },
    ],
  });

  assert.equal(comments[0].user_id, "5efb4b8b00000000010068f6");
});

test("popup imports from the page main world and permits direct backend API base", () => {
  const popupSource = readFileSync(join(import.meta.dirname, "popup.js"), "utf8");
  const manifest = JSON.parse(readFileSync(join(import.meta.dirname, "manifest.json"), "utf8"));

  assert.match(popupSource, /world:\s*"MAIN"/);
  assert.ok(manifest.host_permissions.includes("http://127.0.0.1:18081/*"));
  assert.ok(manifest.host_permissions.includes("http://localhost:18081/*"));
});
