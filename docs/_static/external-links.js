/*
 * Open every off-site link in a new browser tab.
 *
 * The portal embeds its dashboards and PDFs inline; this export links to them
 * instead, so a plain link would navigate the reader away from the docs. Any
 * link whose host differs from the docs' own host gets target="_blank".
 */
document.addEventListener("DOMContentLoaded", function () {
  var links = document.querySelectorAll("article a[href], .content a[href]");
  links.forEach(function (link) {
    var href = link.getAttribute("href");
    if (!href || href.startsWith("#")) {
      return;
    }
    var url;
    try {
      url = new URL(href, window.location.href);
    } catch (e) {
      return;
    }
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      return;
    }
    if (url.host === window.location.host) {
      return;
    }
    link.setAttribute("target", "_blank");
    link.setAttribute("rel", "noopener noreferrer");
  });
});
