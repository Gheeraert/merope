(function () {
  var links = Array.prototype.slice.call(document.querySelectorAll("a.lightbox-link"));
  if (!links.length) {
    return;
  }

  var grouped = new Map();
  links.forEach(function (link) {
    var group = link.getAttribute("data-lightbox-group") || "default";
    if (!grouped.has(group)) {
      grouped.set(group, []);
    }
    grouped.get(group).push(link);
  });

  var state = {
    group: "",
    index: 0,
  };

  var overlay = document.createElement("div");
  overlay.className = "lightbox-overlay";
  overlay.setAttribute("hidden", "hidden");
  overlay.innerHTML =
    '<div class="lightbox-backdrop" data-close="1"></div>' +
    '<div class="lightbox-panel" role="dialog" aria-modal="true" aria-label="Image agrandie">' +
    '<button type="button" class="lightbox-close" data-close="1" aria-label="Fermer">×</button>' +
    '<button type="button" class="lightbox-prev" aria-label="Image précédente">‹</button>' +
    '<figure class="lightbox-figure"><img class="lightbox-image" alt=""><figcaption class="lightbox-caption"></figcaption></figure>' +
    '<button type="button" class="lightbox-next" aria-label="Image suivante">›</button>' +
    "</div>";
  document.body.appendChild(overlay);

  var imageNode = overlay.querySelector(".lightbox-image");
  var captionNode = overlay.querySelector(".lightbox-caption");
  var prevButton = overlay.querySelector(".lightbox-prev");
  var nextButton = overlay.querySelector(".lightbox-next");

  function openLightbox(group, index) {
    state.group = group;
    state.index = index;
    renderCurrent();
    overlay.removeAttribute("hidden");
    document.body.classList.add("lightbox-open");
  }

  function closeLightbox() {
    overlay.setAttribute("hidden", "hidden");
    document.body.classList.remove("lightbox-open");
  }

  function renderCurrent() {
    var groupItems = grouped.get(state.group) || [];
    if (!groupItems.length) {
      closeLightbox();
      return;
    }

    if (state.index < 0) {
      state.index = groupItems.length - 1;
    }
    if (state.index >= groupItems.length) {
      state.index = 0;
    }

    var link = groupItems[state.index];
    imageNode.src = link.getAttribute("href") || "";
    imageNode.alt = (link.querySelector("img") && link.querySelector("img").alt) || "";
    captionNode.textContent = link.getAttribute("data-lightbox-caption") || "";

    var multi = groupItems.length > 1;
    prevButton.hidden = !multi;
    nextButton.hidden = !multi;
  }

  function move(offset) {
    state.index += offset;
    renderCurrent();
  }

  links.forEach(function (link) {
    link.addEventListener("click", function (event) {
      event.preventDefault();
      var group = link.getAttribute("data-lightbox-group") || "default";
      var groupItems = grouped.get(group) || [];
      var idx = groupItems.indexOf(link);
      openLightbox(group, idx < 0 ? 0 : idx);
    });
  });

  overlay.addEventListener("click", function (event) {
    if (event.target.closest("[data-close='1']")) {
      closeLightbox();
    }
  });

  prevButton.addEventListener("click", function () {
    move(-1);
  });

  nextButton.addEventListener("click", function () {
    move(1);
  });

  document.addEventListener("keydown", function (event) {
    if (overlay.hasAttribute("hidden")) {
      return;
    }
    if (event.key === "Escape") {
      closeLightbox();
    } else if (event.key === "ArrowLeft") {
      move(-1);
    } else if (event.key === "ArrowRight") {
      move(1);
    }
  });
})();
