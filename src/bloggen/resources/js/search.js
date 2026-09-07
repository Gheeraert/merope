(function () {
  var container = document.querySelector(".site-search");
  if (!container) {
    return;
  }

  var input = container.querySelector(".site-search-input");
  var resultsList = container.querySelector(".site-search-results");
  var indexHref = container.getAttribute("data-index-href") || "";
  var assetPrefix = container.getAttribute("data-asset-prefix") || "";
  if (!input || !resultsList || !indexHref) {
    return;
  }

  var MAX_RESULTS = 8;
  var TITLE_MATCH_WEIGHT = 10;
  var entries = null;
  var loadingPromise = null;
  var loadFailed = false;

  function normalize(value) {
    return (value || "")
      .toString()
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .toLowerCase();
  }

  function splitWords(query) {
    return normalize(query)
      .split(/\s+/)
      .filter(function (word) {
        return word.length > 0;
      });
  }

  function countOccurrences(haystack, needle) {
    if (!needle) {
      return 0;
    }
    var count = 0;
    var from = 0;
    var at;
    while ((at = haystack.indexOf(needle, from)) !== -1) {
      count += 1;
      from = at + needle.length;
    }
    return count;
  }

  function resolveUrl(rootRelativeUrl) {
    var trimmed = (rootRelativeUrl || "").replace(/^\//, "");
    if (!assetPrefix || assetPrefix === ".") {
      return trimmed;
    }
    return assetPrefix.replace(/\/$/, "") + "/" + trimmed;
  }

  function loadIndex() {
    if (loadingPromise) {
      return loadingPromise;
    }
    loadingPromise = fetch(indexHref)
      .then(function (response) {
        if (!response.ok) {
          throw new Error("search-index fetch failed: " + response.status);
        }
        return response.json();
      })
      .then(function (data) {
        entries = Array.isArray(data)
          ? data.map(function (entry) {
              return {
                title: entry.title || "",
                url: entry.url || "",
                excerpt: entry.excerpt || "",
                normalizedTitle: normalize(entry.title || ""),
                normalizedText: normalize((entry.title || "") + " " + (entry.text || "")),
              };
            })
          : [];
        loadFailed = false;
        return entries;
      })
      .catch(function () {
        entries = [];
        loadFailed = true;
        return entries;
      });
    return loadingPromise;
  }

  // Every query word must appear somewhere in the entry (title or body) —
  // plain substring matching, no stemming/morphological variants, but this
  // already rules out far more noise than matching the query as one single
  // literal phrase. Ranked by a simple relevance score (title hits weigh
  // more than body hits, repeated occurrences count) rather than left in
  // whatever order the index happened to list entries.
  function matchAndScore(loadedEntries, words) {
    var scored = [];
    for (var i = 0; i < loadedEntries.length; i += 1) {
      var entry = loadedEntries[i];
      var score = 0;
      var matchesAll = true;
      for (var w = 0; w < words.length; w += 1) {
        var word = words[w];
        var titleHits = countOccurrences(entry.normalizedTitle, word);
        var textHits = countOccurrences(entry.normalizedText, word);
        if (titleHits === 0 && textHits === 0) {
          matchesAll = false;
          break;
        }
        score += titleHits * TITLE_MATCH_WEIGHT + textHits;
      }
      if (matchesAll) {
        scored.push({ entry: entry, score: score, index: i });
      }
    }
    scored.sort(function (a, b) {
      if (b.score !== a.score) {
        return b.score - a.score;
      }
      return a.index - b.index; // stable: keep original order among ties
    });
    return scored.map(function (item) {
      return item.entry;
    });
  }

  function renderResults(matches) {
    resultsList.innerHTML = "";
    if (!matches.length) {
      resultsList.hidden = true;
      return;
    }
    matches.slice(0, MAX_RESULTS).forEach(function (entry) {
      var item = document.createElement("li");
      item.className = "site-search-result";
      var link = document.createElement("a");
      link.href = resolveUrl(entry.url);
      link.textContent = entry.title;
      var excerpt = document.createElement("p");
      excerpt.className = "site-search-excerpt";
      excerpt.textContent = entry.excerpt;
      item.appendChild(link);
      item.appendChild(excerpt);
      resultsList.appendChild(item);
    });
    resultsList.hidden = false;
  }

  function renderError() {
    resultsList.innerHTML = "";
    var item = document.createElement("li");
    item.className = "site-search-result site-search-error";
    item.textContent = "Recherche indisponible pour le moment.";
    resultsList.appendChild(item);
    resultsList.hidden = false;
  }

  function runSearch(query) {
    var words = splitWords(query);
    if (!words.length) {
      renderResults([]);
      return;
    }
    loadIndex().then(function (loadedEntries) {
      if (loadFailed) {
        renderError();
        return;
      }
      renderResults(matchAndScore(loadedEntries, words));
    });
  }

  input.addEventListener("input", function () {
    runSearch(input.value);
  });

  container.addEventListener("focusout", function () {
    window.setTimeout(function () {
      if (!container.contains(document.activeElement)) {
        resultsList.hidden = true;
      }
    }, 100);
  });

  input.addEventListener("focus", function () {
    if (input.value.trim()) {
      runSearch(input.value);
    }
  });
})();
