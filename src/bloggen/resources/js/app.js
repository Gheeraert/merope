(function () {
  document.documentElement.classList.add("js-enabled");

  var anchorLinks = document.querySelectorAll('a[href^="#note-"], a[href^="#note-call-"], a[href^="#margin-note-"]');
  anchorLinks.forEach(function (link) {
    link.addEventListener("click", function () {
      var targetId = link.getAttribute("href").slice(1);
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
})();
