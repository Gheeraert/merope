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

  // Splits a query into match tokens: a "quoted phrase" becomes ONE token
  // (its internal whitespace collapsed, so it must appear as a continuous
  // run in an entry, in that exact word order), everything else outside
  // quotes is split into individual words as before (each must appear
  // somewhere, in any order — see matchAndScore's AND-of-tokens logic,
  // which needs no change: it already does substring matching per token,
  // so a multi-word phrase token works the same way a single word did).
  function tokenizeQuery(query) {
    var normalized = normalize(query);
    var tokens = [];
    var pattern = /"([^"]*)"|(\S+)/g;
    var match;
    while ((match = pattern.exec(normalized)) !== null) {
      if (match[1] !== undefined) {
        var phrase = match[1].replace(/\s+/g, " ").trim();
        if (phrase) {
          tokens.push(phrase);
        }
      } else if (match[2]) {
        tokens.push(match[2]);
      }
    }
    return tokens;
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

  // Every query token (a plain word, or a whole "quoted phrase" — see
  // tokenizeQuery) must appear somewhere in the entry (title or body) —
  // plain substring matching, no stemming/morphological variants, but this
  // already rules out far more noise than matching the query as one single
  // literal phrase. Ranked by a simple relevance score (title hits weigh
  // more than body hits, repeated occurrences count) rather than left in
  // whatever order the index happened to list entries.
  function matchAndScore(loadedEntries, tokens) {
    var scored = [];
    for (var i = 0; i < loadedEntries.length; i += 1) {
      var entry = loadedEntries[i];
      var score = 0;
      var matchesAll = true;
      for (var t = 0; t < tokens.length; t += 1) {
        var token = tokens[t];
        var titleHits = countOccurrences(entry.normalizedTitle, token);
        var textHits = countOccurrences(entry.normalizedText, token);
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

  // Wraps every match of any token in <mark>, built as real DOM nodes
  // (never innerHTML) so the entry's own title/excerpt text can't be
  // misread as markup. Matching is done on the normalized (accent/case
  // -folded) text to find positions, then sliced out of the ORIGINAL
  // text so the visible highlight keeps its real casing and accents —
  // this assumes normalize() never changes a string's length (true for
  // the NFD-then-strip-combining-marks approach on precomposed French
  // text, which is what the generated site's own title/excerpt strings
  // already are).
  function highlightMatches(text, tokens) {
    var normalizedText = normalize(text);
    var ranges = [];
    tokens.forEach(function (token) {
      if (!token) {
        return;
      }
      var from = 0;
      var at;
      while ((at = normalizedText.indexOf(token, from)) !== -1) {
        ranges.push([at, at + token.length]);
        from = at + token.length;
      }
    });
    var fragment = document.createDocumentFragment();
    if (!ranges.length) {
      fragment.appendChild(document.createTextNode(text));
      return fragment;
    }
    ranges.sort(function (a, b) {
      return a[0] - b[0];
    });
    var merged = [ranges[0].slice()];
    for (var i = 1; i < ranges.length; i += 1) {
      var last = merged[merged.length - 1];
      if (ranges[i][0] <= last[1]) {
        last[1] = Math.max(last[1], ranges[i][1]);
      } else {
        merged.push(ranges[i].slice());
      }
    }
    var cursor = 0;
    merged.forEach(function (range) {
      var start = Math.min(range[0], text.length);
      var end = Math.min(range[1], text.length);
      if (start > cursor) {
        fragment.appendChild(document.createTextNode(text.slice(cursor, start)));
      }
      if (end > start) {
        var mark = document.createElement("mark");
        mark.textContent = text.slice(start, end);
        fragment.appendChild(mark);
      }
      cursor = Math.max(cursor, end);
    });
    if (cursor < text.length) {
      fragment.appendChild(document.createTextNode(text.slice(cursor)));
    }
    return fragment;
  }

  function renderNoResults() {
    resultsList.innerHTML = "";
    var item = document.createElement("li");
    item.className = "site-search-result site-search-empty";
    item.textContent = "Aucun résultat.";
    resultsList.appendChild(item);
    resultsList.hidden = false;
  }

  function renderResults(matches, tokens) {
    resultsList.innerHTML = "";
    if (!matches.length) {
      // Distinguishes "nothing typed yet" (list simply stays hidden) from
      // "typed something, found nothing" (previously indistinguishable —
      // the results list was just silently hidden either way, leaving a
      // visitor who searched for something with no results at all with no
      // feedback that their search actually ran).
      if (tokens && tokens.length) {
        renderNoResults();
      } else {
        resultsList.hidden = true;
      }
      return;
    }
    matches.slice(0, MAX_RESULTS).forEach(function (entry) {
      var item = document.createElement("li");
      item.className = "site-search-result";
      var link = document.createElement("a");
      link.href = resolveUrl(entry.url);
      link.appendChild(highlightMatches(entry.title, tokens));
      var excerpt = document.createElement("p");
      excerpt.className = "site-search-excerpt";
      excerpt.appendChild(highlightMatches(entry.excerpt, tokens));
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
    var tokens = tokenizeQuery(query);
    if (!tokens.length) {
      renderResults([], tokens);
      return;
    }
    loadIndex().then(function (loadedEntries) {
      if (loadFailed) {
        renderError();
        return;
      }
      renderResults(matchAndScore(loadedEntries, tokens), tokens);
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
