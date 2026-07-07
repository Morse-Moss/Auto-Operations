(() => {
const ACTION = "XHS_CURRENT_NOTE_IMPORTER_EXTRACT";

function asText(value) {
  return typeof value === "string" ? value.trim() : "";
}

function unwrap(value) {
  if (value && typeof value === "object" && "_rawValue" in value) {
    return unwrap(value._rawValue);
  }
  if (Array.isArray(value)) {
    return value.map(unwrap);
  }
  if (value && typeof value === "object") {
    const result = {};
    for (const [key, child] of Object.entries(value)) {
      result[key] = unwrap(child);
    }
    return result;
  }
  return value;
}

function unique(values) {
  const seen = new Set();
  const result = [];
  for (const value of values) {
    const cleaned = asText(value);
    if (!cleaned || seen.has(cleaned)) continue;
    seen.add(cleaned);
    result.push(cleaned);
  }
  return result;
}

function xhsMediaKey(url) {
  const match = asText(url).match(/(notes(?:_[^/]+)*\/[^!?#/]+)/);
  return match ? match[1] : asText(url);
}

function looksLikeNoteImageUrl(url) {
  const cleaned = asText(url);
  if (!cleaned || cleaned.startsWith("data:") || cleaned.startsWith("blob:")) return false;
  if (!/xhscdn\.com|xiaohongshu\.com/.test(cleaned)) return false;
  if (/\/avatar\/|\/comment\/|fe-platform/.test(cleaned)) return false;
  return /notes(?:_[^/]+)*\/[^!?#/]+|sns-(webpic|img)|ci\.xiaohongshu/.test(cleaned);
}

function cleanExternalId(value) {
  return asText(value).split("?")[0].split("#")[0].slice(0, 128);
}

function uniqueMediaUrls(values) {
  const seen = new Set();
  const result = [];
  for (const value of values) {
    const cleaned = asText(value);
    const key = xhsMediaKey(cleaned);
    if (!cleaned || seen.has(key)) continue;
    seen.add(key);
    result.push(cleaned);
  }
  return result;
}

function currentNoteId(locationLike) {
  const match = locationLike.pathname.match(/\/explore\/([^/?#]+)/);
  return match ? match[1] : "";
}

function findStateNote(stateLike, noteId) {
  const state = unwrap(stateLike || {});
  return (
    state?.note?.noteDetailMap?.[noteId]?.note ||
    state?.noteData?.data?.noteData ||
    state?.note?.noteDetailMap?.[noteId] ||
    null
  );
}

function imageUrlFromInfoList(image) {
  const infoList = Array.isArray(image?.infoList)
    ? image.infoList
    : Array.isArray(image?.info_list)
      ? image.info_list
      : [];
  if (!infoList.length) return "";
  const defaultInfo =
    infoList.find((info) => ["WB_DFT", "DFT", "DEFAULT"].includes(asText(info?.imageScene || info?.image_scene).toUpperCase())) ||
    infoList.find((info) => asText(info?.url));
  return asText(defaultInfo?.url);
}

function imageUrlsFromNote(note) {
  const imageList = Array.isArray(note?.imageList)
    ? note.imageList
    : Array.isArray(note?.image_list)
      ? note.image_list
      : [];
  const urls = [];
  for (const image of imageList) {
    urls.push(
      image?.urlDefault,
      image?.url_default,
      imageUrlFromInfoList(image),
      image?.url,
      image?.urlPre,
      image?.url_pre,
    );
  }
  return uniqueMediaUrls(urls);
}

function tagsFromNote(note) {
  const tags = Array.isArray(note?.tagList)
    ? note.tagList
    : Array.isArray(note?.tag_list)
      ? note.tag_list
      : [];
  return unique(tags.map((tag) => tag?.name || tag?.tagName || tag?.tag_name || tag));
}

function videoUrlFromNote(note, documentLike) {
  if (asText(note?.type) && asText(note.type) !== "video") {
    return "";
  }
  const streams = [
    note?.video?.media?.stream?.h265,
    note?.video?.media?.stream?.h264,
    note?.video?.stream?.h265,
    note?.video?.stream?.h264,
  ];
  for (const group of streams) {
    if (!Array.isArray(group)) continue;
    for (const stream of group) {
      const url = asText(stream?.masterUrl || stream?.master_url || stream?.backupUrls?.[0] || stream?.backup_urls?.[0]);
      if (url) return url;
    }
  }
  const video = documentLike?.querySelector?.("video");
  const domUrl = asText(video?.currentSrc || video?.src);
  return domUrl && !domUrl.startsWith("blob:") ? domUrl : "";
}

function urlsFromSrcset(value) {
  const entries = asText(value)
    .split(",")
    .map((item) => {
      const [url, descriptor = ""] = item.trim().split(/\s+/);
      const score = Number.parseFloat(descriptor) || 0;
      return { url, score };
    })
    .filter((entry) => entry.url);
  if (!entries.some((entry) => entry.score > 0)) {
    return entries.map((entry) => entry.url);
  }
  return [entries.sort((left, right) => right.score - left.score)[0].url];
}

function urlsFromStyle(value) {
  return Array.from(asText(value).matchAll(/url\((['"]?)(.*?)\1\)/g), (match) => match[2]);
}

function imageUrlsFromDom(documentLike) {
  const urls = [];
  for (const img of Array.from(documentLike?.images || [])) {
    const candidates = [
      img.currentSrc,
      img.src,
      img.getAttribute?.("src"),
      img.getAttribute?.("data-src"),
      img.getAttribute?.("data-original"),
      ...urlsFromSrcset(img.getAttribute?.("srcset") || img.srcset),
    ];
    for (const src of candidates) {
      if (looksLikeNoteImageUrl(src)) {
        urls.push(src);
      }
    }
  }
  for (const node of Array.from(documentLike?.querySelectorAll?.("[style], [data-src], [data-original], [srcset]") || [])) {
    const candidates = [
      node.getAttribute?.("data-src"),
      node.getAttribute?.("data-original"),
      ...urlsFromSrcset(node.getAttribute?.("srcset")),
      ...urlsFromStyle(node.getAttribute?.("style")),
      ...urlsFromStyle(node.style?.backgroundImage),
    ];
    for (const src of candidates) {
      if (looksLikeNoteImageUrl(src)) {
        urls.push(src);
      }
    }
  }
  return uniqueMediaUrls(urls);
}

function visibleComments(documentLike) {
  const comments = [];
  const nodes = Array.from(documentLike?.querySelectorAll?.("[id^='comment-']") || []);
  for (const node of nodes.slice(0, 50)) {
    const commentId = asText(node.id).replace(/^comment-/, "");
    const content =
      asText(node.querySelector?.(".content")?.textContent) ||
      asText(node.querySelector?.(".comment-content")?.textContent) ||
      asText(node.textContent);
    if (!content) continue;
    const userLink = node.querySelector?.("a[href*='/user/profile/']");
    const userHref = userLink?.getAttribute?.("href") || "";
    comments.push({
      comment_id: commentId || `visible-${comments.length + 1}`,
      user_name: asText(userLink?.textContent),
      user_id: cleanExternalId(userHref.split("/").filter(Boolean).pop() || ""),
      content,
      like_count: 0,
      created_at_remote: "",
      raw: { visible: true },
    });
  }
  return comments;
}

function extractCurrentNote({ locationLike, documentLike, initialState }) {
  const noteId = currentNoteId(locationLike);
  if (!noteId) {
    throw new Error("Open an XHS /explore note page first.");
  }
  const note = findStateNote(initialState, noteId) || {};
  const images = imageUrlsFromNote(note);
  const domImages = imageUrlsFromDom(documentLike);
  const fallbackImages = uniqueMediaUrls([...images, ...domImages]);
  return {
    note_id: noteId,
    note_url: locationLike.href,
    title: asText(note.title) || asText(documentLike?.querySelector?.("#detail-title, .title")?.textContent) || documentLike?.title || "",
    content: asText(note.desc) || asText(note.description) || asText(documentLike?.querySelector?.("#detail-desc, .desc")?.textContent),
    author_name: asText(note.user?.nickname || note.user?.nickName || note.user?.name),
    author_id: asText(note.user?.userId || note.user?.user_id || note.user?.id),
    tags: tagsFromNote(note),
    image_urls: fallbackImages,
    video_url: videoUrlFromNote(note, documentLike),
    video_cover_url: fallbackImages[0] || "",
    visible_comments: visibleComments(documentLike),
    raw: {
      note_type: note.type || "",
      source_url: locationLike.href,
      extracted_from: "current_page",
    },
  };
}

globalThis.XhsCurrentNoteImporter = {
  ACTION,
  asText,
  unwrap,
  unique,
  xhsMediaKey,
  looksLikeNoteImageUrl,
  cleanExternalId,
  uniqueMediaUrls,
  currentNoteId,
  findStateNote,
  imageUrlFromInfoList,
  imageUrlsFromNote,
  tagsFromNote,
  videoUrlFromNote,
  imageUrlsFromDom,
  visibleComments,
  extractCurrentNote,
};
})();
