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
  var entries = null;
  var loadingPromise = null;

  function normalize(value) {
    return (value || "")
      .toString()
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .toLowerCase();
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
                normalizedText: normalize((entry.title || "") + " " + (entry.text || "")),
              };
            })
          : [];
        return entries;
      })
      .catch(function () {
        entries = [];
        return entries;
      });
    return loadingPromise;
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

  function runSearch(query) {
    var needle = normalize(query);
    if (!needle) {
      renderResults([]);
      return;
    }
    loadIndex().then(function (loadedEntries) {
      var matches = loadedEntries.filter(function (entry) {
        return entry.normalizedText.indexOf(needle) !== -1;
      });
      renderResults(matches);
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
