/**
 * PO Lifecycle D3 visual — live version for the exception dashboard.
 *
 * Reads lifecycle numbers from the #lifecycle-data JSON block injected
 * server-side. Falls back to the canonical example (150/138/150/131)
 * when the DB is not connected.
 *
 * Callout boxes are clickable — clicking one fetches matching exception
 * orders from /api/lifecycle/drilldown and displays them below the visual.
 *
 * Requires D3 v7 on the page before this script loads.
 * Renders into #lifecycle-visual.
 */
(function () {
  "use strict";

  var CANONICAL = {
    ordered: 150, shipped: 138, invoiced: 150, paid: 131,
    callouts: [{count: 12, dollars: 1800}, {count: 12, dollars: 2100}, {count: 19, dollars: 2400}],
    source: "canonical"
  };

  var C = {
    canvas:   "#f5f3ee",
    ink:      "#0d0d0d",
    border:   "#d9d9d9",
    sub:      "#595959",
    muted:    "#b3b3b3",
    navy:     "#1f2e7a",
    rose:     "#b82d4a",
    roseSurf: "#fbe9ed",
    roseBrd:  "#e68a9a",
    orange:   "#ee8a2a",
    orSurf:   "#fdeee0",
    orBrd:    "#f6b97c",
    serif:    "'Playfair Display', Georgia, serif",
    sans:     "'Source Sans 3', 'Source Sans Pro', 'Helvetica Neue', Arial, sans-serif",
  };

  var W = 1120, H = 540;
  var BOX_W = 170, BOX_H = 145;
  var BOX_TOP = 88;
  var BOX_CX = [130, 390, 650, 910];
  var ARROW_Y = BOX_TOP + BOX_H / 2;
  var CALL_TOP = BOX_TOP + BOX_H + 24;
  var CALL_W = 190, CALL_H = 130;

  var CALLOUT_LABELS = [
    "Ordered, Not ASN'd",
    "Shipped, Not Invoiced",
    "Short Pay",
  ];

  var STAGES = [
    { key: "ordered",  label: "ORDERED",  color: C.ink    },
    { key: "shipped",  label: "SHIPPED",  color: C.rose   },
    { key: "invoiced", label: "INVOICED", color: C.orange },
    { key: "paid",     label: "PAID",     color: C.rose   },
  ];

  var currentPartner = "";
  try {
    var pEl = document.getElementById("lifecycle-partner");
    if (pEl) currentPartner = JSON.parse(pEl.textContent) || "";
  } catch (_) {}

  var PAGE_SIZE = 100;
  var activeData = null;                                  // last-rendered data, for callout dollar totals
  var dd = { callout: null, offset: 0, loaded: 0, total: 0 };  // drill-down pagination state

  function fmtCompact(n) {
    var abs = Math.abs(n);
    if (abs >= 1e6) return (n / 1e6).toFixed(1) + "M";
    if (abs >= 10000) return (n / 1e3).toFixed(1) + "K";
    return n.toLocaleString();
  }

  function fmtDollarCompact(n) {
    var abs = Math.abs(n);
    if (abs >= 1e6) return "$" + (abs / 1e6).toFixed(1) + "M";
    if (abs >= 1e3) return "$" + (abs / 1e3).toFixed(1) + "K";
    return "$" + abs.toFixed(0);
  }

  function fontSizeForValue(n) {
    if (Math.abs(n) >= 1e6) return "36px";
    if (Math.abs(n) >= 10000) return "40px";
    return "48px";
  }

  function fmtCalloutCount(n) {
    return n + " order" + (n === 1 ? "" : "s");
  }

  function calloutDesc(i, data) {
    if (i === 0) return ["not shipped", "OTIF exposure"];
    if (i === 1) return data.invoiced > data.shipped
      ? ["invoiced without ASN", "chargeback exposure"]
      : ["ASN qty > invoice qty", "shipped-not-invoiced"];
    return ["short-paid on remittance", "30-day dispute window"];
  }

  function render(data) {
    var container = document.getElementById("lifecycle-visual");
    if (!container) return;
    activeData = data;
    container.innerHTML = "";

    var svg = d3.select(container)
      .append("svg")
      .attr("viewBox", "0 0 " + W + " " + H)
      .attr("width", "100%")
      .style("max-width", W + "px")
      .style("display", "block")
      .attr("role", "img")
      .attr("aria-label",
        "PO Lifecycle: " + data.ordered + " ordered, " + data.shipped + " shipped, " +
        data.invoiced + " invoiced, " + data.paid + " paid");

    svg.append("rect").attr("width", W).attr("height", H).attr("fill", C.canvas);

    svg.append("text")
      .attr("x", 20).attr("y", 32)
      .style("font-family", C.serif)
      .style("font-size", "18px")
      .style("font-weight", "700")
      .style("fill", C.ink)
      .text("PO Lifecycle — Four-Way EDI Match");

    svg.append("text")
      .attr("x", 20).attr("y", 54)
      .style("font-family", C.sans)
      .style("font-size", "13px")
      .style("fill", C.sub)
      .text(data.source === "live"
        ? "Live from exception mart (edi_marts.int_four_way_match)"
        : data.source === "validation-fallback"
          ? "Canonical example — live data failed validation (PAID > INVOICED)"
          : "Canonical example — connect to Postgres and run dbt for live numbers");

    STAGES.forEach(function (stage, i) {
      var cx = BOX_CX[i];
      var bx = cx - BOX_W / 2;

      svg.append("rect")
        .attr("x", bx).attr("y", BOX_TOP)
        .attr("width", BOX_W).attr("height", BOX_H)
        .attr("fill", "#ffffff")
        .attr("stroke", C.border)
        .attr("stroke-width", 1)
        .attr("rx", 2);

      svg.append("text")
        .attr("x", cx).attr("y", BOX_TOP + 22)
        .attr("text-anchor", "middle")
        .style("font-family", C.sans)
        .style("font-size", "10px")
        .style("letter-spacing", "0.07em")
        .style("fill", C.sub)
        .text(stage.label);

      var val = data[stage.key];
      svg.append("text")
        .attr("x", cx).attr("y", BOX_TOP + 88)
        .attr("text-anchor", "middle")
        .style("font-family", C.serif)
        .style("font-size", fontSizeForValue(val))
        .style("font-weight", "700")
        .style("fill", stage.color)
        .text(fmtCompact(val));

      svg.append("text")
        .attr("x", cx).attr("y", BOX_TOP + 112)
        .attr("text-anchor", "middle")
        .style("font-family", C.sans)
        .style("font-size", "13px")
        .style("fill", C.sub)
        .text("cases");
    });

    var callouts = data.callouts || [
      {count: 0, dollars: 0}, {count: 0, dollars: 0}, {count: 0, dollars: 0}
    ];

    for (var i = 0; i < 3; i++) {
      var x1 = BOX_CX[i]     + BOX_W / 2;
      var x2 = BOX_CX[i + 1] - BOX_W / 2;
      var mx = (x1 + x2) / 2;

      svg.append("line")
        .attr("x1", x1).attr("y1", ARROW_Y)
        .attr("x2", x2 - 8).attr("y2", ARROW_Y)
        .attr("stroke", C.border)
        .attr("stroke-width", 1.5);

      svg.append("polygon")
        .attr("points", x2 + "," + ARROW_Y + " " + (x2 - 10) + "," + (ARROW_Y - 5) + " " + (x2 - 10) + "," + (ARROW_Y + 5))
        .attr("fill", C.border);

      svg.append("line")
        .attr("x1", mx).attr("y1", BOX_TOP + BOX_H + 2)
        .attr("x2", mx).attr("y2", CALL_TOP - 2)
        .attr("stroke", C.border)
        .attr("stroke-width", 1)
        .attr("stroke-dasharray", "3,3");

      var co = callouts[i];
      var hasIssues = co.count > 0;
      var style = hasIssues
        ? { fill: C.roseSurf, stroke: C.roseBrd, color: C.rose }
        : { fill: "#ffffff",  stroke: C.border,  color: C.sub  };

      // Clickable callout group
      var calloutGroup = svg.append("g")
        .style("cursor", hasIssues ? "pointer" : "default")
        .attr("data-callout", i);

      calloutGroup.append("rect")
        .attr("x", mx - CALL_W / 2).attr("y", CALL_TOP)
        .attr("width", CALL_W).attr("height", CALL_H)
        .attr("fill", style.fill)
        .attr("stroke", style.stroke)
        .attr("stroke-width", 1)
        .attr("rx", 2);

      var calloutLabel = co.dollars > 0
        ? "−" + fmtDollarCompact(co.dollars)
        : fmtCalloutCount(co.count);

      calloutGroup.append("text")
        .attr("x", mx).attr("y", CALL_TOP + 38)
        .attr("text-anchor", "middle")
        .style("font-family", C.serif)
        .style("font-size", "28px")
        .style("font-weight", "700")
        .style("fill", style.color)
        .text(calloutLabel);

      var descs = calloutDesc(i, data);
      calloutGroup.append("text")
        .attr("x", mx).attr("y", CALL_TOP + 62)
        .attr("text-anchor", "middle")
        .style("font-family", C.sans)
        .style("font-size", "14px")
        .style("fill", C.sub)
        .text(descs[0]);

      calloutGroup.append("text")
        .attr("x", mx).attr("y", CALL_TOP + 82)
        .attr("text-anchor", "middle")
        .style("font-family", C.sans)
        .style("font-size", "13px")
        .style("fill", C.muted)
        .text(descs[1]);

      if (hasIssues) {
        calloutGroup.append("text")
          .attr("x", mx).attr("y", CALL_TOP + CALL_H - 10)
          .attr("text-anchor", "middle")
          .style("font-family", C.sans)
          .style("font-size", "11px")
          .style("fill", C.navy)
          .style("text-decoration", "underline")
          .text("view orders ›");
      }

      (function(idx, active) {
        if (active) calloutGroup.on("click", function() { loadDrilldown(idx); });
      })(i, hasIssues);
    }

    svg.append("line")
      .attr("x1", 20).attr("y1", H - 32)
      .attr("x2", W - 20).attr("y2", H - 32)
      .attr("stroke", C.border)
      .attr("stroke-width", 1);

    svg.append("text")
      .attr("x", 20).attr("y", H - 16)
      .style("font-family", C.sans)
      .style("font-size", "11px")
      .style("fill", C.muted)
      .text("Synthetic corpus" +
        (data.partner_labels && data.partner_labels.length
          ? " — " + data.partner_labels.join(" · ") : "") +
        ". UoM normalized to cases before comparison.");
  }

  function rowHtml(row) {
    var html = "<tr>";
    html += '<td><span class="partner-badge">' + esc(row.partner_label) + "</span></td>";
    html += '<td><span class="chip chip--' + esc(row.exception_class) + '">' + esc(row.class_label) + "</span></td>";
    html += "<td>" + esc(row.po_display || "—") + "</td>";
    html += "<td>" + esc(row.sku || "—") + "</td>";
    html += "<td>" + esc(row.invoice_display || "—") + "</td>";
    html += '<td class="td--dollar">' + esc(row.dollar_fmt) + "</td>";
    html += "<td>";
    if (row.dispute_urgent) {
      html += '<span class="urgent-badge">' + esc(row.dispute_window_expires_at || "—") + "</span>";
    } else if (row.dispute_window_expires_at) {
      html += '<span class="expired-badge">' + esc(row.dispute_window_expires_at) + "</span>";
    } else {
      html += '<span style="color:#595959;">—</span>';
    }
    return html + "</td></tr>";
  }

  function updateDrilldownMeta() {
    var meta = document.getElementById("drilldown-meta");
    var loadBtn = document.getElementById("drilldown-loadmore");
    if (meta) {
      var dollars = (activeData && activeData.callouts && activeData.callouts[dd.callout])
        ? activeData.callouts[dd.callout].dollars : 0;
      var dollarStr = dollars > 0 ? " · " + fmtDollarCompact(dollars) + " total exposure" : "";
      meta.textContent = dd.total > 0
        ? "Showing " + dd.loaded.toLocaleString() + " of " + dd.total.toLocaleString() + " orders" + dollarStr
        : "";
    }
    if (loadBtn) {
      loadBtn.style.display = (dd.loaded < dd.total) ? "inline-block" : "none";
      loadBtn.textContent = "Load next " + Math.min(PAGE_SIZE, dd.total - dd.loaded);
    }
  }

  function fetchDrilldownPage(append) {
    var tbody = document.getElementById("drilldown-rows");
    if (!tbody) return;

    var url = "/api/lifecycle/drilldown?callout=" + dd.callout + "&offset=" + dd.offset;
    if (currentPartner) url += "&partner=" + encodeURIComponent(currentPartner);

    fetch(url)
      .then(function(r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(function(res) {
        var rows = (res && res.rows) || [];
        dd.total = (res && res.total) || 0;
        if (!append && rows.length === 0) {
          tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:20px;color:#595959;">No matching orders found.</td></tr>';
          updateDrilldownMeta();
          return;
        }
        var html = "";
        for (var i = 0; i < rows.length; i++) html += rowHtml(rows[i]);
        if (append) tbody.insertAdjacentHTML("beforeend", html);
        else tbody.innerHTML = html;
        dd.loaded += rows.length;
        dd.offset += rows.length;
        updateDrilldownMeta();
      })
      .catch(function() {
        if (!append) {
          tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:20px;color:#b82d4a;">Failed to load drill-down data.</td></tr>';
        }
      });
  }

  function loadDrilldown(calloutIndex) {
    var section = document.getElementById("lifecycle-drilldown");
    var title = document.getElementById("drilldown-title");
    var tbody = document.getElementById("drilldown-rows");
    var meta = document.getElementById("drilldown-meta");
    if (!section || !title || !tbody) return;

    dd = { callout: calloutIndex, offset: 0, loaded: 0, total: 0 };
    title.textContent = CALLOUT_LABELS[calloutIndex] + " — Matching Orders";
    if (meta) meta.textContent = "";
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:20px;color:#595959;">Loading…</td></tr>';
    section.style.display = "block";
    section.scrollIntoView({ behavior: "smooth", block: "start" });

    fetchDrilldownPage(false);
  }

  function esc(s) {
    var d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
  }

  // Close button
  var closeBtn = document.getElementById("drilldown-close");
  if (closeBtn) {
    closeBtn.addEventListener("click", function() {
      var section = document.getElementById("lifecycle-drilldown");
      if (section) section.style.display = "none";
    });
  }

  // Load-next-page button
  var loadMoreBtn = document.getElementById("drilldown-loadmore");
  if (loadMoreBtn) {
    loadMoreBtn.addEventListener("click", function() {
      if (dd.callout !== null) fetchDrilldownPage(true);
    });
  }

  function isValid(d) {
    if (!d || typeof d.ordered !== "number" || d.ordered <= 0) return false;
    if (d.paid > d.invoiced) return false;
    if (!d.callouts || d.callouts.length < 3) return false;
    return true;
  }

  var el = document.getElementById("lifecycle-data");
  var serverData = null;
  try { serverData = el ? JSON.parse(el.textContent) : null; } catch (_) {}

  // Distinguish "no server data" (empty {} when DB is absent) from
  // "live data present but failed validation" (e.g. PAID > INVOICED).
  var hasLiveData = serverData && typeof serverData.ordered === "number";

  var data;
  if (hasLiveData && isValid(serverData)) {
    data = serverData;
  } else {
    data = Object.assign({}, CANONICAL);
    if (hasLiveData) data.source = "validation-fallback";
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { render(data); });
  } else {
    render(data);
  }

}());
