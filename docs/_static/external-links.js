/*
 * Open external links and PDF documents in a new browser tab.
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

    // Open all PDF files in a new tab
    if (url.pathname.toLowerCase().endsWith(".pdf")) {
      link.setAttribute("target", "_blank");
      link.setAttribute("rel", "noopener noreferrer");
      return;
    }

    // Ignore non-web links
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      return;
    }

    // Open external websites in a new tab
    if (url.host !== window.location.host) {
      link.setAttribute("target", "_blank");
      link.setAttribute("rel", "noopener noreferrer");
    }
  });
});