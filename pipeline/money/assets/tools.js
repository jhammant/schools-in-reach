/* School Money — tools.js (globalThis.MoneyTools). Defer-loaded on /tools/ pages, after app.js; every tool page
   explains itself in server-rendered text and works as a plain page without it.
   Pure helpers (an exact port of status.py, forecasts, the PTA planner, the embed code) are exported and tested
   under node (pipeline/money/test_tools_js.mjs). DOM wiring runs only in a browser. All data goes into the page
   through textContent / setAttribute: no HTML is built from data.

   Reads (this site only): /data/s/<urn>.json, /data/sx/<urn>.json, /data/a/<id>.json, and the page's
   <script type="application/json" id="tools-context"> block (IFS framings with page numbers, from guides.py).
   Stores: localStorage moneyToolsDraft (form drafts, on this device only). Sends nothing anywhere. */
(function (root) {
  "use strict";

  // ======================================================================
  // status.py, ported line for line (keep the two in step)
  // ======================================================================
  var ORDER = ["in_deficit", "heading_for_deficit", "tight", "healthy", "large_reserves"];
  var LABELS = { in_deficit: "In deficit", heading_for_deficit: "Heading for deficit", tight: "Tight", healthy: "Healthy", large_reserves: "Large reserves" };
  var ICONS = { in_deficit: "▼", heading_for_deficit: "↘", tight: "●", healthy: "✓", large_reserves: "▲" };
  var TIGHT_BELOW = 0.03;
  var LARGE_FROM = { secondary: 0.05, "default": 0.08 };
  var RUNWAY_YEARS = 3;
  var has = Object.prototype.hasOwnProperty;

  // Python's f"{x:.Nf}" for N = 0 or 1. toFixed rounds an exact tie away from zero; Python takes the even
  // digit. A tie at N decimals happens exactly when x * 2^(N+1) is an odd integer.
  function pyFixed(x, digits) {
    var negative = x < 0 || (x === 0 && 1 / x < 0);
    var a = Math.abs(x), text = a.toFixed(digits), t = a * Math.pow(2, digits + 1);
    if (Math.floor(t) === t && t % 2 === 1) {
      var scale = Math.pow(10, digits), low = Math.floor(a * scale);
      if (low % 2 === 0) text = digits === 0 ? String(low) : Math.floor(low / scale) + "." + (low % scale);
    }
    return (negative ? "-" : "") + text;
  }
  function pyPercent(x) { return pyFixed(x * 100, 0) + "%"; }   // f"{x:.0%}" multiplies first, then rounds

  // status._money
  function money(value) {
    var sign = value < 0 ? "-" : "";
    value = Math.abs(value);
    if (value >= 1000000) return sign + "£" + pyFixed(value / 1000000, 1) + "m";
    if (value >= 1000) return sign + "£" + pyFixed(value / 1000, 0) + "k";
    return sign + "£" + pyFixed(value, 0);
  }

  // Python's sum() for floats (3.12+): Neumaier-compensated. For whole-pound figures every order is exact.
  function pySum(values) {
    var total = 0, c = 0;
    for (var i = 0; i < values.length; i++) {
      var x = values[i], t = total + x;
      c += Math.abs(total) >= Math.abs(x) ? (total - t) + x : (x - t) + total;
      total = t;
    }
    return c && isFinite(c) ? total + c : total;
  }

  function fullYears(rows) {
    var byEnd = Object.create(null), keys = [];
    (Array.isArray(rows) ? rows : []).forEach(function (r) {
      if (!r || r.did_not_supply || r.period_months !== 12 || !r.total_income || r.revenue_reserve == null) return;
      var key = String(r.period_end);
      if (!(key in byEnd)) keys.push(key);
      byEnd[key] = r;
    });
    keys.sort();
    return keys.map(function (k) { return byEnd[k]; });
  }

  function reserveShare(row) {
    var reserve = row.revenue_reserve_incl_trust_share;
    if (reserve == null) reserve = row.revenue_reserve;
    var income = row.total_income;
    if (reserve == null || !income) return null;
    return reserve / income;
  }

  function deficitStreak(years) {
    var streak = 0;
    for (var i = years.length - 1; i >= 0; i--) {
      if ((years[i].in_year_balance || 0) < 0) streak++;
      else break;
    }
    return streak;
  }

  function assess(rows) {
    var years = fullYears(rows);
    if (!years.length) return null;
    var latest = years[years.length - 1];
    var share = reserveShare(latest);
    var reserve = latest.revenue_reserve_incl_trust_share;
    if (reserve == null) reserve = latest.revenue_reserve;
    var streak = deficitStreak(years);
    var phase = latest.phase || "default";
    var largeFrom = has.call(LARGE_FROM, phase) ? LARGE_FROM[phase] : LARGE_FROM["default"];
    var pupilsChange = null, first = null;
    for (var i = 0; i < years.length; i++) { if (years[i].pupils) { first = years[i]; break; } }
    if (first && latest.pupils && first !== latest) pupilsChange = latest.pupils / first.pupils - 1;

    var recent = years.slice(-3);
    var avgOverspend = -pySum(recent.map(function (r) { return r.in_year_balance || 0; })) / recent.length;
    var runway = reserve > 0 && avgOverspend > 0 ? reserve / avgOverspend : null;

    var status, reason;
    if (reserve < 0) {
      status = "in_deficit";
      reason = "In deficit by " + money(-reserve) + ", " + pyPercent(Math.abs(share)) + " of a year's income: it has spent more over the years than it received.";
      if (streak >= 2) reason += " It has spent more than it received for " + streak + " years running.";
    } else if (streak >= 2 && runway != null && runway <= RUNWAY_YEARS) {
      status = "heading_for_deficit";
      reason = "Has spent more than it received for " + streak + " years running; at that rate " +
        "its " + money(reserve) + " reserve runs out in about " + pyFixed(Math.max(runway, 0.5), 0) + " year" + (runway >= 1.5 ? "s" : "") + ".";
    } else if (share < TIGHT_BELOW) {
      status = "tight";
      reason = "Holds " + money(reserve) + " in reserve, under 3% of a year's income: little room for surprises.";
    } else if (share >= largeFrom) {
      status = "large_reserves";
      reason = "Holds " + money(reserve) + " in reserve, " + pyPercent(share) + " of a year's income.";
      if (streak >= 2) reason += " It has been drawing on it for " + streak + " years.";
    } else {
      status = "healthy";
      reason = "Holds " + money(reserve) + " in reserve, " + pyPercent(share) + " of a year's income.";
      if (streak >= 2) reason += " It has spent more than it received for " + streak + " years, so watch the trend.";
    }
    return {
      status: status, label: LABELS[status], rank: ORDER.indexOf(status), reason: reason,
      year: latest.year, source: latest.source, reserve: reserve, reserve_share: share, deficit_streak: streak,
      runway_years: runway, pupils_change: pupilsChange, years: years.length,
      trust_share_included: latest.revenue_reserve_incl_trust_share != null
    };
  }

  // ======================================================================
  // Formatting and small helpers
  // ======================================================================
  var BASE = "https://money.schoolsinreach.com";
  var SITE_NAME = "School Money";
  var FBIT = "https://financial-benchmarking-and-insights-tool.education.gov.uk/";
  var REGISTER = "https://register-of-charities.charitycommission.gov.uk/charity-search/-/charity-details/";
  var DRAFT_KEY = "moneyToolsDraft";
  var SOURCE_NAMES = { CFR: "DfE CFR return", AAR: "DfE academy accounts return" };
  var PTA_SOURCE = "Charity Commission register";

  function toNum(v) {
    if (typeof v === "number") return isFinite(v) ? v : null;
    if (v == null) return null;
    var s = String(v).trim().replace(/[£,\s]/g, "").replace(/^\((.*)\)$/, "-$1").replace(/^[−–]/, "-");
    if (!s) return null;
    var m = /^(-?\d+(?:\.\d+)?|-?\.\d+)([km])?$/i.exec(s);
    if (!m) return null;
    var n = parseFloat(m[1]);
    if (m[2]) n *= m[2].toLowerCase() === "k" ? 1e3 : 1e6;
    return isFinite(n) ? n : null;
  }
  function app() { return root.MoneyApp || null; }
  function fmtMoney(v) {
    if (app() && app().fmtMoney) return app().fmtMoney(v);
    if (typeof v !== "number" || !isFinite(v)) return "—";
    return money(v);
  }
  // £4,115 style, to the pound (MoneyApp has no exact formatter).
  function fmtExact(v, signed) {
    if (typeof v !== "number" || !isFinite(v)) return "—";
    var sign = v < 0 ? "-" : (signed && v > 0 ? "+" : "");
    return sign + "£" + Math.round(Math.abs(v)).toLocaleString("en-GB");
  }
  function fmtPupils(n) {
    if (typeof n !== "number" || !isFinite(n)) return "—";
    return (Math.round(n * 10) / 10).toLocaleString("en-GB", { maximumFractionDigits: 1 });
  }
  function sourceName(src) {
    if (src == null || src === "") return null;
    return has.call(SOURCE_NAMES, src) ? SOURCE_NAMES[src] : String(src);
  }
  function escAttr(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function cleanUrn(u) {
    var s = String(u == null ? "" : u).trim();
    return /^\d{5,8}$/.test(s) ? s : null;
  }
  function cleanAreaId(id) {
    var s = String(id == null ? "" : id).trim().toLowerCase();
    return /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(s) ? s : null;
  }
  function councilAreaId(code) {
    var s = String(code == null ? "" : code).trim();
    return /^[A-Za-z0-9]+$/.test(s) ? "council-" + s : null;
  }
  // "2025-26" -> "2026-27"; "2024/25" -> "2025/26".
  function nextYearLabel(label) {
    var m = /^(\d{4})([-\/])(\d{2}|\d{4})$/.exec(String(label == null ? "" : label).trim());
    if (!m) return null;
    var start = parseInt(m[1], 10) + 1, end = start + 1;
    return start + m[2] + (m[3].length === 2 ? ("0" + (end % 100)).slice(-2) : String(end));
  }
  function nextPeriodEnd(end) {
    var m = /^(\d{4})(.*)$/.exec(String(end == null ? "" : end));
    return m ? (parseInt(m[1], 10) + 1) + m[2] : null;
  }
  // Financial years end in March (CFR), academy years in August (AAR).
  function periodEndFor(label, academy) {
    var m = /^(\d{4})[-\/]\d{2,4}$/.exec(String(label == null ? "" : label).trim());
    return m ? (parseInt(m[1], 10) + 1) + (academy ? "-08-31" : "-03-31") : null;
  }
  function flaggedYears(flags) {
    var out = [];
    function add(y) { if (y != null && out.indexOf(String(y)) === -1) out.push(String(y)); }
    if (Array.isArray(flags)) flags.forEach(function (f) { add(f && typeof f === "object" ? f.year : f); });
    else if (flags && typeof flags === "object") Object.keys(flags).forEach(function (y) {
      var v = flags[y];
      if (v && (!Array.isArray(v) || v.length)) add(y);
    });
    return out;
  }
  function firstKey(obj, keys) {
    if (!obj || typeof obj !== "object") return null;
    for (var i = 0; i < keys.length; i++) if (obj[keys[i]] != null) return obj[keys[i]];
    return null;
  }

  // ======================================================================
  // The ONE adapter for /data/s, /data/sx and /data/a documents: every field read happens here.
  // ======================================================================
  function adapt(s, sx, area) {
    var out = { school: null, history: [], flagged: [], source: null, area: null };
    s = s && typeof s === "object" ? s : null;
    sx = sx && typeof sx === "object" ? sx : null;
    if (s) {
      var council = s.council && typeof s.council === "object" ? s.council : {};
      var tags = s.tags && typeof s.tags === "object" ? s.tags : {};
      out.school = {
        urn: s.urn != null ? String(s.urn) : null, name: s.name ? String(s.name) : null, path: s.path || null,
        council: { code: council.code != null ? String(council.code) : null, name: council.name || null, path: council.path || null },
        status: has.call(LABELS, s.status) ? s.status : null, label: s.label || null, reason: s.reason || null, year: s.year || null,
        academy: !!s.academy, pupils: toNum(s.pupils), band: toNum(s.band),
        phase: s.phase || tags.phase || null,
        pta: (Array.isArray(s.pta) ? s.pta : []).filter(function (c) { return c && !c.review; }).map(function (c) {
          var hist = (Array.isArray(c.history) ? c.history : []).filter(function (h) { return h && h.period_end; })
            .sort(function (a, b) { return String(a.period_end) < String(b.period_end) ? -1 : 1; });
          var last = hist.length ? hist[hist.length - 1] : null;
          return { number: c.charity_number != null ? String(c.charity_number) : null, name: c.name || "Parents' association",
            status: c.status || null, income: last && toNum(last.income) != null ? toNum(last.income) : toNum(c.latest_income),
            period_end: last ? String(last.period_end) : null };
        })
      };
    }
    var academy = out.school ? out.school.academy : false;
    var sxSource = sx && sx.source != null ? String(sx.source) : null;
    if (sxSource && /AAR|academ/i.test(sxSource)) academy = true;
    out.source = sxSource || (academy ? "AAR" : "CFR");
    out.flagged = sx ? flaggedYears(sx.flags) : [];

    // Years: /data/sx metrics first, then /data/s years[] for anything missing.
    var byYear = {}, labels = [];
    function row(y) {
      if (!has.call(byYear, y)) { byYear[y] = { year: y }; labels.push(y); }
      return byYear[y];
    }
    var m = sx && sx.m && typeof sx.m === "object" ? sx.m : {};
    function cell(metric, y) {
      var c = m[metric] && m[metric][y];
      return c && typeof c === "object" ? toNum(c.v) : null;
    }
    if (sx && Array.isArray(sx.years)) sx.years.forEach(function (y) {
      var r = row(String(y));
      r.total_income = cell("total_income", y); r.total_expenditure = cell("total_expenditure", y);
      r.revenue_reserve = cell("revenue_reserve", y); r.in_year_balance = cell("in_year_balance", y);
      r.pupils = sx.pupils && typeof sx.pupils === "object" ? toNum(sx.pupils[y]) : null;
    });
    if (s && Array.isArray(s.years)) s.years.forEach(function (y) {
      if (!y || y.y == null) return;
      var r = row(String(y.y));
      if (r.total_income == null) r.total_income = toNum(y.income);
      if (r.total_expenditure == null) r.total_expenditure = toNum(y.spend);
      if (r.revenue_reserve == null) r.revenue_reserve = toNum(y.reserve);
      if (r.in_year_balance == null) r.in_year_balance = toNum(y.balance);
      if (r.pupils == null) r.pupils = toNum(y.pupils);
    });
    var phase = out.school ? out.school.phase : null;
    labels.sort();
    out.history = labels.map(function (y) { return byYear[y]; }).filter(function (r) {
      return r.total_income != null && r.revenue_reserve != null;
    }).map(function (r) {
      if (r.in_year_balance == null && r.total_expenditure != null) r.in_year_balance = r.total_income - r.total_expenditure;
      r.period_end = periodEndFor(r.year, academy) || r.year;
      r.period_months = 12;
      r.source = out.source;
      if (phase) r.phase = phase;
      if (out.flagged.indexOf(r.year) !== -1) r.flagged = true;
      return r;
    });

    area = area && typeof area === "object" ? area : null;
    if (area) {
      var A = area;
      var years = A.by_year && typeof A.by_year === "object" ? Object.keys(A.by_year).sort() : [];
      var found = null;
      for (var i = years.length - 1; i >= 0 && !found; i--) {
        var S = A.by_year[years[i]] && A.by_year[years[i]].all;
        var median = toNum(firstKey(S, ["pta_pp_median", "pta_median_pp"]));
        if (median != null) {
          found = { year: years[i], median_pp: median, schools: toNum(firstKey(S, ["pta_schools"])),
            band_medians: firstKey(S, ["pta_pp_median_by_band", "pta_median_pp_by_band", "pta_pp_median_band", "fsm_band_pta_pp_median"]) };
        }
      }
      out.area = { id: A.id || null, name: A.name || "this area", path: A.path || null,
        year: found ? found.year : null, median_pp: found ? found.median_pp : null, schools: found ? found.schools : null,
        band_medians: found && found.band_medians && typeof found.band_medians === "object" ? found.band_medians : null };
    }
    return out;
  }

  // History rows for the budget check, from /data/sx (preferred) and /data/s.
  function prefillFrom(sx, s) {
    var a = adapt(s, sx, null);
    return { rows: a.history, flagged: a.flagged, source: a.source, school: a.school };
  }

  // ======================================================================
  // Budget check
  // ======================================================================
  // Up to three projected 12-month rows after the last full year of history: in_year_balance = income - spend,
  // reserve = the previous reserve + that balance unless a reserve is given.
  function projectRows(history, future) {
    var past = fullYears(history);
    var last = past.length ? past[past.length - 1] : null;
    var reserve = last ? (last.revenue_reserve_incl_trust_share != null ? last.revenue_reserve_incl_trust_share : last.revenue_reserve) : 0;
    var year = last ? last.year : null, end = last ? last.period_end : null, out = [];
    var list = Array.isArray(future) ? future.slice(0, 3) : [];
    for (var i = 0; i < list.length; i++) {
      var f = list[i] || {}, income = toNum(f.income), spend = toNum(f.spend);
      if (income == null || spend == null) break;
      var balance = income - spend, given = toNum(f.reserve);
      reserve = given != null ? given : reserve + balance;
      year = nextYearLabel(year) || "Year " + (i + 1);
      end = nextPeriodEnd(end) || "Y" + (i + 1);
      var r = { year: year, period_end: end, period_months: 12, total_income: income, total_expenditure: spend,
        in_year_balance: balance, revenue_reserve: reserve, source: "Your forecast", projected: true };
      var pupils = toNum(f.pupils) != null ? toNum(f.pupils) : (last ? last.pupils : null);
      if (pupils != null) r.pupils = pupils;
      if (last && last.phase) r.phase = last.phase;
      out.push(r);
    }
    return out;
  }

  function framing(ctx, key) {
    var f = ctx && ctx.ifs && ctx.ifs.framings && ctx.ifs.framings[key];
    return f && f.text ? { title: f.title || "", text: f.text + " (IFS 2026 report, " + f.pages + ")" } : null;
  }

  // The status for each projected year, the runway and a plain explanation of what it means and what helps.
  function budgetCheck(history, future, ctx) {
    var past = fullYears(history);
    var rows = projectRows(past, future);
    var now = assess(past);
    var years = rows.map(function (row, i) {
      var r = assess(past.concat(rows.slice(0, i + 1)));
      return { year: row.year, income: row.total_income, spend: row.total_expenditure, balance: row.in_year_balance,
        reserve: row.revenue_reserve, status: r ? r.status : null, label: r ? r.label : null, reason: r ? r.reason : null, result: r };
    });
    var end = years.length ? years[years.length - 1].result : now;
    var firstDeficit = null, overspends = 0;
    years.forEach(function (y) {
      if (firstDeficit == null && y.reserve < 0) firstDeficit = y.year;
      if (y.balance < 0) overspends++;
    });
    var summary, text = [], helps = [], context = [];
    if (!now) {
      summary = "Enter the last full year's income, spending and reserve to start.";
    } else if (!years.length) {
      summary = "In " + now.year + ": " + now.label + ". " + now.reason + " Add the next year's income and spending to see a forecast.";
    } else {
      var lastYear = years[years.length - 1];
      summary = "By the end of " + lastYear.year + ", on these figures: " + lastYear.label + ". " + lastYear.reason;
      var back = null;
      years.forEach(function (y) { if (back == null && y.reserve >= 0) back = y.year; });
      if (now.reserve < 0 && back) text.push("On these figures the reserve would be back above zero by the end of " + back + ".");
      else if (now.reserve < 0) text.push("On these figures the reserve would still be below zero at the end of " + lastYear.year + ". A recovery plan sets out the steps and how many years they will take.");
      else if (firstDeficit) text.push("The reserve would go below zero in " + firstDeficit + ". This is a forecast, and forecasts can change: the earlier a gap is spotted, the more ways there are to close it.");
      else if (overspends) text.push("Spending would be higher than income in " + overspends + " of the " + years.length + " years, but the reserve would stay above zero.");
      else text.push("Income would cover spending in every year of the forecast.");
      if (end && end.runway_years != null && end.status !== "in_deficit") {
        text.push("At the average overspend of the last three years, the reserve would last about " + pyFixed(Math.max(end.runway_years, 0.5), 0) + " more year" + (end.runway_years >= 1.5 ? "s" : "") + ".");
      }
    }
    var status = end ? end.status : null;
    if (status === "in_deficit" || status === "heading_for_deficit") {
      context.push(framing(ctx, "why_schools_go_into_deficit"));
      helps.push("Talk to the school business manager and the governors' finance committee early: a gap two years away has more answers than one two months away.");
      helps.push("A council-run school works with the council under its scheme for financing schools, which asks for a recovery plan when a deficit rises above 5%. An academy works with its trust.");
      helps.push("The DfE's school resource management advisers give schools and trusts expert advice on using their money, and its buying service and Energy for schools can help bring costs down.");
    } else if (status === "tight") {
      helps.push("A reserve under 3% of a year's income leaves little room for surprises, such as a pay award above the plan. Check which costs are most likely to rise.");
      helps.push("Ask whether the budget relies on one-off grants or fundraising to balance.");
    } else if (status === "large_reserves") {
      helps.push("A large reserve is often kept for a reason, such as building work or a planned overspend. Governors can ask what it is for and when it will be used.");
    } else if (status === "healthy") {
      helps.push("A reserve of 3% or more of a year's income, and under 8% (5% for secondaries), counts as healthy on this site.");
    }
    if (overspends && status !== "in_deficit") context.push(framing(ctx, "one_deficit_year"));
    var falling = (now && now.pupils_change != null && now.pupils_change <= -0.05) ||
      rows.some(function (r) { return now && past.length && r.pupils != null && past[past.length - 1].pupils && r.pupils < past[past.length - 1].pupils * 0.95; });
    if (falling) context.push(framing(ctx, "falling_rolls"));
    return {
      now: now, years: years, status: status, runway_years: end ? end.runway_years : null, first_deficit_year: firstDeficit,
      summary: summary, explanation: text, helps: helps, context: context.filter(Boolean),
      links: [{ text: "Guide for governors: questions and recovery plans", href: "/guides/governors/" },
        { text: "How to read a deficit", href: "/guides/parents/#how-to-read-a-deficit" }]
    };
  }

  // ======================================================================
  // PTA planner
  // ======================================================================
  function planPta(input) {
    input = input || {};
    var events = (Array.isArray(input.events) ? input.events : []).map(function (e, i) {
      e = e || {};
      var income = toNum(e.income) || 0, donations = toNum(e.donations) || 0;
      return { name: String(e.name == null ? "" : e.name).trim() || "Event " + (i + 1), income: income, donations: donations, total: income + donations };
    }).filter(function (e) { return e.total !== 0; });
    var income = pySum(events.map(function (e) { return e.income; }));
    var donations = pySum(events.map(function (e) { return e.donations; }));
    var share = toNum(input.giftAidShare);
    share = share == null ? 0 : Math.min(1, Math.max(0, share));
    var giftAid = 0.25 * donations * share;
    var total = income + donations + giftAid;
    var pupils = toNum(input.pupils);
    if (!(pupils > 0)) pupils = null;
    var targetPp = toNum(input.targetPp);
    if (!(targetPp > 0)) targetPp = null;
    var target = targetPp != null && pupils ? targetPp * pupils : null;
    var gap = target != null ? target - total : null;
    var notes = ["Gift Aid adds 25p to every £1 donated by a UK taxpayer who has signed a Gift Aid declaration. It cannot be claimed on ticket sales, raffles or anything bought (HMRC)."];
    if (donations > 0 && share === 0) notes.push("None of these donations has a Gift Aid declaration yet. Asking donors to sign one could add up to " + fmtExact(0.25 * donations) + ".");
    notes.push("Cash and contactless donations of £30 or less can also earn 25% through the Gift Aid small donations scheme, without declarations (HMRC).");
    if (total > 5000) notes.push("With an income over £5,000 a year, a parents' association that is a charity in England and Wales must register with the Charity Commission.");
    return { events: events, income: income, donations: donations, giftAidShare: share, giftAid: giftAid, total: total,
      pupils: pupils, perPupil: pupils ? total / pupils : null, targetPp: targetPp, target: target, gap: gap,
      gapPp: gap != null ? gap / pupils : null, notes: notes };
  }

  // Compare a plan's £ per pupil with the area's median for registered parents' associations.
  function comparePta(plan, areaDoc, bandMedians) {
    var area = adapt(null, null, areaDoc).area;
    var out = { area: area ? area.name : null, year: area ? area.year : null, medianPp: area ? area.median_pp : null,
      differencePp: null, band: null, bandMedianPp: null, bandAvailable: false, sentences: [] };
    var pp = plan && typeof plan.perPupil === "number" ? plan.perPupil : null;
    if (!area || area.median_pp == null) {
      out.sentences.push("There is no council median for parents' association income to compare with yet. A median is only shown where enough schools have figures.");
    } else {
      out.sentences.push("Registered parents' associations at schools in " + area.name + " raised a median of " + fmtExact(area.median_pp) +
        " per pupil in " + area.year + " (" + PTA_SOURCE + ").");
      if (pp != null) {
        out.differencePp = pp - area.median_pp;
        var diff = Math.round(Math.abs(out.differencePp));
        out.sentences.push(diff === 0 ? "Your plan is about the same per pupil." :
          "Your plan is " + fmtExact(diff) + " per pupil " + (out.differencePp > 0 ? "above" : "below") + " that. Every school community is different, so use it as a rough guide, not a target.");
      }
    }
    var medians = bandMedians && typeof bandMedians === "object" ? bandMedians : (area ? area.band_medians : null);
    var band = plan && toNum(plan.band) != null ? String(toNum(plan.band)) : null;
    // Band medians may be {"1": £, ...} or a list for bands 1 to 5.
    var bandValue = !medians || !band ? null : toNum(Array.isArray(medians) ? medians[Number(band) - 1] : medians[band]);
    if (medians && Object.keys(medians).length) {
      out.bandAvailable = true;
      if (bandValue != null) {
        out.band = Number(band);
        out.bandMedianPp = bandValue;
        out.sentences.push("Schools with a similar intake (band " + band + " of 5 by free school meals, where 1 is the most affluent) had a median of " +
          fmtExact(out.bandMedianPp) + " per pupil (" + PTA_SOURCE + ").");
      } else {
        out.sentences.push("This school's free school meals band isn't known, so the comparison is with every school in the council.");
      }
    } else {
      out.sentences.push("Medians for schools with a similar intake (by free school meals) aren't available yet, so the comparison is with every school in the council.");
    }
    out.sentences.push("Money a parents' association gives the school can also appear in the school's own donations income, so the two are never added together.");
    return out;
  }

  // ======================================================================
  // Embed
  // ======================================================================
  function embedSnippet(urn, name) {
    var u = String(urn == null ? "" : urn).replace(/\D/g, "");
    if (!u) return "";
    return '<iframe src="' + BASE + "/embed/" + escAttr(u) + '/" title="' + escAttr(SITE_NAME + ": " + String(name == null ? "" : name)) +
      '" width="320" height="140" loading="lazy" style="border:0"></iframe>';
  }

  // ======================================================================
  // Fetching: only /data/ paths on this site; every failure resolves to null.
  // ======================================================================
  // rel is a path under /data/, e.g. "sx/130932.json"; anything else (.., //, ?, a scheme) is refused unfetched.
  function getJSON(rel) {
    rel = String(rel == null ? "" : rel);
    if (!/^[a-z0-9][a-z0-9_-]*(?:\/[a-z0-9][a-z0-9_.-]*)*\.json$/i.test(rel) || rel.indexOf("..") !== -1 || typeof fetch !== "function") return Promise.resolve(null);
    return fetch("/data/" + rel).then(function (r) { return r && r.ok ? r.json() : null; })
      .then(function (d) { return d && typeof d === "object" ? d : null; }, function () { return null; });
  }
  function loadSchool(urn) {
    var u = cleanUrn(urn);
    if (!u) return Promise.resolve({ ok: false, message: "That doesn't look like a school URN. It is a number, for example 130932." });
    return Promise.all([getJSON("sx/" + u + ".json"), getJSON("s/" + u + ".json")]).then(function (d) {
      if (!d[0] && !d[1]) return { ok: false, urn: u, message: "Figures for this school aren't published on this site yet. The DfE's Financial Benchmarking and Insights Tool may have them." };
      return { ok: true, urn: u, data: adapt(d[1], d[0], null) };
    });
  }
  function loadArea(id) {
    var a = cleanAreaId(id);
    return a ? getJSON("a/" + a + ".json") : Promise.resolve(null);
  }

  var API = {
    ORDER: ORDER, LABELS: LABELS, ICONS: ICONS, TIGHT_BELOW: TIGHT_BELOW, LARGE_FROM: LARGE_FROM, RUNWAY_YEARS: RUNWAY_YEARS,
    BASE: BASE, pyFixed: pyFixed, money: money, fullYears: fullYears, reserveShare: reserveShare, deficitStreak: deficitStreak,
    assess: assess, toNum: toNum, fmtExact: fmtExact, fmtPupils: fmtPupils, nextYearLabel: nextYearLabel, flaggedYears: flaggedYears,
    adapt: adapt, prefillFrom: prefillFrom, projectRows: projectRows, budgetCheck: budgetCheck, planPta: planPta,
    comparePta: comparePta, embedSnippet: embedSnippet, getJSON: getJSON, loadSchool: loadSchool, loadArea: loadArea,
    councilAreaId: councilAreaId
  };
  root.MoneyTools = API;
  if (typeof document === "undefined") return;

  // ======================================================================
  // DOM wiring
  // ======================================================================
  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function link(text, href, external) {
    var a = el("a", null, text);
    a.setAttribute("href", href);
    if (external) a.setAttribute("rel", "noopener");
    return a;
  }
  function badge(status) {
    var b = el("span", "badge small s-" + status), i = el("span", null, ICONS[status] || "");
    i.setAttribute("aria-hidden", "true");
    b.appendChild(i);
    b.appendChild(document.createTextNode(" " + (LABELS[status] || status)));
    return b;
  }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); return node; }
  function context() {
    var node = $("tools-context");
    try { return node ? JSON.parse(node.textContent) : {}; } catch (e) { return {}; }
  }
  function params() {
    var out = {};
    String(location.search || "").replace(/^\?/, "").split("&").forEach(function (kv) {
      if (!kv) return;
      var i = kv.indexOf("="), k = decodeURIComponent(i < 0 ? kv : kv.slice(0, i)), v = i < 0 ? "" : kv.slice(i + 1);
      try { out[k] = decodeURIComponent(v.replace(/\+/g, " ")); } catch (e) { out[k] = ""; }
    });
    return out;
  }
  function readDrafts() {
    try { var d = JSON.parse(localStorage.getItem(DRAFT_KEY) || "{}"); return d && typeof d === "object" ? d : {}; } catch (e) { return {}; }
  }
  function saveDraft(tool, form) {
    var all = readDrafts(), mine = {};
    Array.prototype.forEach.call(form.elements, function (f) { if (f.id && f.type !== "submit" && f.type !== "button") mine[f.id] = f.value; });
    all[tool] = mine;
    try { localStorage.setItem(DRAFT_KEY, JSON.stringify(all)); } catch (e) { /* storage full or blocked: drafts are optional */ }
  }
  function restoreDraft(tool, form) {
    var mine = readDrafts()[tool];
    if (!mine) return;
    Object.keys(mine).forEach(function (id) { var f = $(id); if (f && form.contains(f) && typeof mine[id] === "string") f.value = mine[id]; });
  }
  function dropDraft(tool) {
    var all = readDrafts();
    delete all[tool];
    try { localStorage.setItem(DRAFT_KEY, JSON.stringify(all)); } catch (e) { /* ignore */ }
  }
  function val(id) { var f = $(id); return f ? toNum(f.value) : null; }
  function setVal(id, v) { var f = $(id); if (f && v != null) f.value = typeof v === "number" ? String(Math.round(v * 10) / 10) : String(v); }

  // A small bar chart of the reserve by year; projected years are marked. role=img with every value in its label.
  function reserveChart(points) {
    var NS = "http://www.w3.org/2000/svg", w = 320, h = 150, pad = 22, n = points.length;
    var vals = points.map(function (p) { return p.reserve; });
    var hi = Math.max(0, Math.max.apply(null, vals)), lo = Math.min(0, Math.min.apply(null, vals)), span = hi - lo || 1;
    var svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", "0 0 " + w + " " + h);
    svg.setAttribute("class", "chart tool-chart");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", "Reserve at the end of each year: " + points.map(function (p) {
      return p.year + " " + fmtMoney(p.reserve) + (p.projected ? " (forecast)" : "") + (p.flagged ? " (figures look unusual)" : "");
    }).join("; ") + ".");
    function y(v) { return pad + (hi - v) / span * (h - 2 * pad); }
    var zero = document.createElementNS(NS, "line");
    zero.setAttribute("x1", "0"); zero.setAttribute("x2", String(w)); zero.setAttribute("y1", String(y(0))); zero.setAttribute("y2", String(y(0)));
    zero.setAttribute("class", "axis");
    svg.appendChild(zero);
    var slot = w / Math.max(n, 1);
    points.forEach(function (p, i) {
      var bar = document.createElementNS(NS, "rect"), top = Math.min(y(p.reserve), y(0));
      bar.setAttribute("x", String(i * slot + slot * 0.2)); bar.setAttribute("width", String(slot * 0.6));
      bar.setAttribute("y", String(top)); bar.setAttribute("height", String(Math.max(1, Math.abs(y(p.reserve) - y(0)))));
      bar.setAttribute("class", "bar " + (p.reserve < 0 ? "neg" : "pos") + (p.projected ? " projected" : "") + (p.flagged ? " flagged" : ""));
      svg.appendChild(bar);
      var t = document.createElementNS(NS, "text");
      t.setAttribute("x", String(i * slot + slot / 2)); t.setAttribute("y", String(h - 4)); t.setAttribute("text-anchor", "middle");
      t.setAttribute("class", "tick");
      t.textContent = String(p.year).replace(/^20/, "") + (p.flagged ? " ⚑" : "");
      svg.appendChild(t);
    });
    return svg;
  }

  function wireBudget(ctx) {
    var form = $("bc-form"), loader = $("bc-load"), status = $("bc-load-status"), out = $("bc-out");
    if (!form || !loader || !out) return;
    var state = { history: [], flagged: [], academy: false, name: null, source: null };
    restoreDraft("budget", form);
    loader.addEventListener("submit", function (e) { e.preventDefault(); load($("bc-urn").value); });
    form.addEventListener("input", function () { saveDraft("budget", form); });
    form.addEventListener("submit", function (e) { e.preventDefault(); run(); });
    var clearBtn = form.querySelector("[data-clear]");
    if (clearBtn) clearBtn.addEventListener("click", function () {
      form.reset(); dropDraft("budget"); state.history = []; state.flagged = [];
      clear(out).appendChild(el("p", "muted", "Cleared. Fill in the figures and press Check the budget."));
    });

    function load(urn) {
      status.textContent = "Loading published figures…";
      loadSchool(urn).then(function (res) {
        if (!res.ok) { status.textContent = res.message; return; }
        var d = res.data, last = d.history[d.history.length - 1];
        if (!last) { status.textContent = "Figures for this school aren't published yet, so type in your own below."; return; }
        state.history = d.history; state.flagged = d.flagged; state.source = d.source;
        state.academy = d.school ? d.school.academy : d.source === "AAR";
        state.name = d.school && d.school.name;
        setVal("bc-year", last.year); setVal("bc-income", last.total_income); setVal("bc-spend", last.total_expenditure);
        setVal("bc-reserve", last.revenue_reserve); setVal("bc-pupils", last.pupils);
        if (d.school && d.school.phase && $("bc-phase")) $("bc-phase").value = d.school.phase === "secondary" ? "secondary" : (d.school.phase === "primary" ? "primary" : "default");
        [1, 2, 3].forEach(function (i) {
          if (val("bc-inc-" + i) == null) setVal("bc-inc-" + i, last.total_income);
          if (val("bc-sp-" + i) == null) setVal("bc-sp-" + i, last.total_expenditure);
        });
        var msg = "Loaded " + (state.name || "the school") + ": " + d.history.length + " year" + (d.history.length === 1 ? "" : "s") +
          " of published figures, the latest for " + last.year + " (" + sourceName(d.source) + "). The next three years start flat: change them to your forecast.";
        if (d.flagged.length) msg += " The figures for " + d.flagged.join(", ") + " look unusual and are marked ⚑: check them on the DfE's tool before relying on them.";
        status.textContent = msg;
        saveDraft("budget", form);
      });
    }

    function run() {
      var year = ($("bc-year").value || "").trim(), income = val("bc-income"), spend = val("bc-spend"), reserve = val("bc-reserve");
      clear(out);
      if (!income || reserve == null) { out.appendChild(el("p", null, "Enter last year's income and reserve to start.")); return; }
      var phase = $("bc-phase") ? $("bc-phase").value : "default";
      var end = periodEndFor(year, state.academy) || "0000";
      var lastRow = { year: year || "Last year", period_end: end, period_months: 12, total_income: income, total_expenditure: spend,
        in_year_balance: spend != null ? income - spend : null, revenue_reserve: reserve, pupils: val("bc-pupils"), phase: phase,
        source: state.source || "Your figures", flagged: state.flagged.indexOf(year) !== -1 };
      var past = state.history.filter(function (r) { return String(r.period_end) < end; }).map(function (r) {
        var c = {}; Object.keys(r).forEach(function (k) { c[k] = r[k]; }); c.phase = phase; return c;
      });
      var future = [1, 2, 3].map(function (i) { return { income: val("bc-inc-" + i), spend: val("bc-sp-" + i), reserve: val("bc-res-" + i) }; });
      var res = budgetCheck(past.concat([lastRow]), future, ctx);
      out.appendChild(el("p", "lead", res.summary));
      if (res.now) {
        var nowP = el("p", "status-line");
        nowP.appendChild(document.createTextNode((res.now.year || "Last year") + " (" + (sourceName(res.now.source) || "your figures") + "): "));
        nowP.appendChild(badge(res.now.status));
        nowP.appendChild(document.createTextNode(" " + res.now.reason));
        out.appendChild(nowP);
      }
      if (res.years.length) {
        var list = el("ol", "tool-years");
        res.years.forEach(function (y) {
          var li = el("li");
          li.appendChild(el("strong", null, y.year + " (your forecast) "));
          if (y.status) li.appendChild(badge(y.status));
          li.appendChild(el("span", "tool-figs", " Income " + fmtExact(y.income) + ", spending " + fmtExact(y.spend) + ", balance " +
            fmtExact(y.balance, true) + ", reserve at year end " + fmtExact(y.reserve) + "."));
          if (y.reason) li.appendChild(el("span", "muted small", " " + y.reason));
          list.appendChild(li);
        });
        out.appendChild(list);
        var points = past.concat([lastRow]).slice(-3).map(function (r) { return { year: r.year, reserve: r.revenue_reserve, flagged: !!r.flagged }; })
          .concat(res.years.map(function (y) { return { year: y.year, reserve: y.reserve, projected: true }; }));
        var fig = el("figure", "tool-figure");
        fig.appendChild(reserveChart(points));
        fig.appendChild(el("figcaption", "muted small", "Reserve at the end of each year, cash. Faded bars are your forecast." +
          (points.some(function (p) { return p.flagged; }) ? " ⚑ marks a year whose published figures look unusual." : "")));
        out.appendChild(fig);
      }
      res.explanation.forEach(function (t) { out.appendChild(el("p", null, t)); });
      res.context.forEach(function (c) {
        var note = el("div", "note");
        note.setAttribute("role", "note");
        note.appendChild(el("strong", null, c.title + ". "));
        note.appendChild(document.createTextNode(c.text));
        out.appendChild(note);
      });
      if (res.helps.length) {
        out.appendChild(el("h3", null, "What helps"));
        var ul = el("ul");
        res.helps.forEach(function (t) { ul.appendChild(el("li", null, t)); });
        out.appendChild(ul);
      }
      var more = el("p", "small");
      res.links.forEach(function (l, i) { if (i) more.appendChild(document.createTextNode(" · ")); more.appendChild(link(l.text, l.href)); });
      out.appendChild(more);
      var foot = el("p", "muted small", "Cash figures, as published or as typed. Published years: " + (sourceName(state.source) || "your figures") +
        ". Forecast years are yours. Nothing you typed has left this browser.");
      if (res.context.length && ctx.ifs && ctx.ifs.url) {
        foot.appendChild(document.createTextNode(" Context: "));
        foot.appendChild(link(ctx.ifs.cite || "IFS 2026 report", ctx.ifs.url, true));
        foot.appendChild(document.createTextNode("."));
      }
      out.appendChild(foot);
    }

    var q = params();
    if (cleanUrn(q.urn)) { $("bc-urn").value = q.urn; load(q.urn); }
  }

  function wirePta(ctx) {
    var form = $("pp-form"), loader = $("pp-load"), status = $("pp-load-status"), out = $("pp-out"), box = $("pp-charity");
    if (!form || !loader || !out) return;
    var state = { area: null, band: null };
    restoreDraft("pta", form);
    var events = $("pp-events"), count = events ? events.querySelectorAll("fieldset.event").length : 0;
    loader.addEventListener("submit", function (e) { e.preventDefault(); loadUrn($("pp-urn").value); });
    form.addEventListener("input", function () { saveDraft("pta", form); });
    form.addEventListener("submit", function (e) { e.preventDefault(); run(); });
    var add = $("pp-add");
    if (add && events) add.addEventListener("click", function () {
      count++;
      var fs = el("fieldset", "event"), row = el("div", "field-row");
      fs.appendChild(el("legend", null, "Event " + count));
      [["pp-name-", "Name", ""], ["pp-inc-", "Ticket sales and other takings", "£"], ["pp-don-", "Donations", "£"]].forEach(function (f) {
        var wrap = el("div", "field"), input = el("input"), label = el("label", null, f[1]);
        input.id = f[0] + count; input.name = input.id; input.type = "text"; input.setAttribute("autocomplete", "off");
        if (f[2]) { input.setAttribute("inputmode", "decimal"); input.setAttribute("placeholder", f[2]); }
        label.setAttribute("for", input.id);
        wrap.appendChild(label); wrap.appendChild(input); row.appendChild(wrap);
      });
      fs.appendChild(row); events.appendChild(fs);
      $("pp-name-" + count).focus();
    });
    var clearBtn = form.querySelector("[data-clear]");
    if (clearBtn) clearBtn.addEventListener("click", function () {
      form.reset(); dropDraft("pta");
      clear(out).appendChild(el("p", "muted", "Cleared. Add your events and press Work it out."));
    });

    function showCharities(school) {
      clear(box);
      if (!school) return;
      box.appendChild(el("h2", null, "Parents' association"));
      if (!school.pta.length) {
        box.appendChild(el("p", null, "No registered parents' association found for " + (school.name || "this school") +
          ". Charities with an income of £5,000 or less don't have to register, so a smaller association may still exist."));
        return;
      }
      var ul = el("ul");
      school.pta.forEach(function (c) {
        var li = el("li");
        li.appendChild(c.number ? link(c.name, REGISTER + encodeURIComponent(c.number), true) : el("span", null, c.name));
        if (c.income != null) {
          var pp = school.pupils ? c.income / school.pupils : null;
          li.appendChild(document.createTextNode(": " + (pp != null ? fmtExact(pp) + " per pupil (" + fmtExact(c.income) + " in total)" : fmtExact(c.income)) +
            (c.period_end ? ", year to " + c.period_end : "") + ", " + PTA_SOURCE + "."));
        }
        ul.appendChild(li);
      });
      box.appendChild(ul);
      box.appendChild(el("p", "muted small", "The association's income and the school's donations can overlap, so they are never added together."));
    }
    function loadUrn(urn) {
      status.textContent = "Loading the school…";
      loadSchool(urn).then(function (res) {
        if (!res.ok) { status.textContent = res.message; return; }
        var school = res.data.school;
        if (!school) { status.textContent = "This school's details aren't published yet."; return; }
        if (school.pupils != null) setVal("pp-pupils", Math.round(school.pupils * 10) / 10);
        state.band = school.band;
        showCharities(school);
        var id = councilAreaId(school.council.code);
        status.textContent = "Loaded " + (school.name || "the school") + (school.pupils != null ? ", " + fmtPupils(school.pupils) + " pupils" : "") + ".";
        if (id) loadArea(id).then(function (doc) {
          state.area = doc;
          if (!doc) status.textContent += " Council figures aren't published yet, so there is no comparison.";
        });
        saveDraft("pta", form);
      });
    }
    function run() {
      var list = [];
      for (var i = 1; i <= count; i++) list.push({ name: ($("pp-name-" + i) || {}).value, income: val("pp-inc-" + i), donations: val("pp-don-" + i) });
      var gift = val("pp-gift");
      var plan = planPta({ events: list, pupils: val("pp-pupils"), giftAidShare: gift == null ? null : gift / 100, targetPp: val("pp-target") });
      plan.band = state.band;
      clear(out);
      if (!plan.events.length) { out.appendChild(el("p", null, "Add the amount for at least one event.")); return; }
      out.appendChild(el("p", "lead", plan.perPupil != null ?
        fmtExact(plan.perPupil) + " per pupil (" + fmtExact(plan.total) + " in total, with Gift Aid)." :
        fmtExact(plan.total) + " in total, with Gift Aid. Add the number of pupils to see it per pupil."));
      var dl = el("dl", "tool-sums");
      [["Ticket sales and takings", fmtExact(plan.income)], ["Donations", fmtExact(plan.donations)],
        ["Gift Aid (" + Math.round(plan.giftAidShare * 100) + "% of donations declared)", fmtExact(plan.giftAid)]].forEach(function (r) {
        dl.appendChild(el("dt", null, r[0])); dl.appendChild(el("dd", null, r[1]));
      });
      out.appendChild(dl);
      if (plan.gap != null) out.appendChild(el("p", null, plan.gap > 0 ?
        "To reach your target of " + fmtExact(plan.targetPp) + " per pupil, you would need another " + fmtExact(plan.gapPp) + " per pupil (" + fmtExact(plan.gap) + ")." :
        "That meets your target of " + fmtExact(plan.targetPp) + " per pupil."));
      if (state.area) comparePta(plan, state.area).sentences.forEach(function (t) { out.appendChild(el("p", null, t)); });
      var ul = el("ul", "small");
      plan.notes.forEach(function (t) { ul.appendChild(el("li", null, t)); });
      out.appendChild(ul);
      out.appendChild(el("p", "muted small", "Your plan stays in this browser. Comparison figures: " + PTA_SOURCE + "."));
    }

    var q = params();
    if (cleanUrn(q.urn)) { $("pp-urn").value = q.urn; loadUrn(q.urn); }
    else if (cleanAreaId(q.area)) loadArea(q.area).then(function (doc) {
      state.area = doc;
      status.textContent = doc ? "Comparing with " + (adapt(null, null, doc).area.name) + "." : "Figures for this area aren't published yet.";
    });
  }

  function wireEmbed() {
    var loader = $("em-load"), status = $("em-load-status"), code = $("em-code"), copy = $("em-copy"), done = $("em-copied"), frame = $("em-preview");
    if (!loader || !code) return;
    loader.addEventListener("submit", function (e) { e.preventDefault(); make($("em-urn").value); });
    function make(urn) {
      status.textContent = "Looking up the school…";
      loadSchool(urn).then(function (res) {
        if (!res.ok) { status.textContent = res.message; return; }
        var school = res.data.school;
        if (!school || !school.status) {
          status.textContent = "This school doesn't have a published money status yet, so there is no badge to embed.";
          return;
        }
        code.value = embedSnippet(res.urn, school.name || res.urn);
        status.textContent = "Here is the code for " + (school.name || "the school") + ".";
        frame.setAttribute("src", "/embed/" + res.urn + "/");
        frame.hidden = false;
        if ($("em-empty")) $("em-empty").hidden = true;
      });
    }
    if (copy) copy.addEventListener("click", function () {
      if (!code.value) { done.textContent = "Make the code first."; return; }
      function fallback() {
        code.focus(); code.select();
        var ok = false;
        try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
        done.textContent = ok ? "Copied." : "Select the code above and copy it.";
      }
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(code.value).then(function () { done.textContent = "Copied."; }, fallback);
      else fallback();
    });
    var q = params();
    if (cleanUrn(q.urn)) { $("em-urn").value = q.urn; make(q.urn); }
  }

  function init() {
    var ctx = context();
    Array.prototype.forEach.call(document.querySelectorAll("[data-tool]"), function (box) { box.hidden = false; });
    wireBudget(ctx);
    wirePta(ctx);
    wireEmbed();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})(typeof globalThis !== "undefined" ? globalThis : this);
