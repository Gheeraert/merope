(function () {
  document.documentElement.classList.add("js-enabled");

  var anchorLinks = document.querySelectorAll('a[href^="#note-"], a[href^="#note-call-"], a[href^="#margin-note-"]');
  anchorLinks.forEach(function (link) {
    link.addEventListener("click", function () {
      var href = link.getAttribute("href") || "";
      if (!href || href.charAt(0) !== "#") {
        return;
      }
      var targetId = href.slice(1);
      window.setTimeout(function () {
        var target = document.getElementById(targetId);
        if (!target) {
          return;
        }
        target.classList.add("is-targeted");
        window.setTimeout(function () {
          target.classList.remove("is-targeted");
        }, 900);
      }, 80);
    });
  });

  var noteCalls = document.querySelectorAll(".note-call-link[data-margin-note-target]");
  noteCalls.forEach(function (call) {
    var targetId = call.getAttribute("data-margin-note-target");
    if (!targetId) {
      return;
    }

    var margin = document.getElementById(targetId);
    if (!margin) {
      return;
    }

    var toggle = function (active) {
      margin.classList.toggle("is-targeted", active);
      call.classList.toggle("is-targeted", active);
    };

    call.addEventListener("mouseenter", function () {
      toggle(true);
    });
    call.addEventListener("mouseleave", function () {
      toggle(false);
    });
    call.addEventListener("focus", function () {
      toggle(true);
    });
    call.addEventListener("blur", function () {
      toggle(false);
    });
  });
})();
