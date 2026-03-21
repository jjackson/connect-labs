/**
 * Funder Dashboard — Chart Rendering
 *
 * Vanilla JS (no build step). Expects window.Chart (Chart.js 4.x) and
 * window.L (Leaflet 1.9.x + MarkerCluster) to be loaded before this file.
 *
 * Exports four top-level functions consumed by the SSE client in the template:
 *   renderKPIs(visits, payments, container)
 *   renderVisitsChart(visits)
 *   renderPaymentsChart(payments)
 *   renderMap(visits)
 */

/* eslint-disable no-var */
/* global Chart, L */

var OPP_COLORS = [
  '#6366f1',
  '#10b981',
  '#f59e0b',
  '#ef4444',
  '#8b5cf6',
  '#06b6d4',
  '#ec4899',
  '#84cc16',
  '#f97316',
  '#14b8a6',
  '#a855f7',
  '#64748b',
  '#e11d48',
  '#0ea5e9',
  '#22c55e',
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Group a flat array of rows by opp_id, returning { [oppId]: { rows, opp_name, country, delivery_type } }. */
function groupByOpp(rows) {
  var result = {};
  for (var i = 0; i < rows.length; i++) {
    var r = rows[i];
    var id = String(r.opp_id);
    if (!result[id]) {
      result[id] = {
        rows: [],
        opp_name: r.opp_name || 'Opp ' + id,
        country: r.country || '',
        delivery_type: r.delivery_type || '',
      };
    }
    result[id].rows.push(r);
  }
  return result;
}

/** Return ISO week-start (Monday) string for a date. */
function weekStart(dateStr) {
  var d = new Date(dateStr);
  if (isNaN(d.getTime())) return null;
  var day = d.getDay();
  var diff = (day === 0 ? -6 : 1) - day; // Monday
  d.setDate(d.getDate() + diff);
  return d.toISOString().slice(0, 10);
}

/** Get sorted unique week-start strings from an array of date strings. */
function uniqueWeeks(dates) {
  var set = {};
  for (var i = 0; i < dates.length; i++) {
    var ws = weekStart(dates[i]);
    if (ws) set[ws] = true;
  }
  return Object.keys(set).sort();
}

/** Assign a consistent color index for an opp id. */
var _oppColorMap = {};
var _oppColorIdx = 0;
function oppColor(oppId) {
  if (_oppColorMap[oppId] === undefined) {
    _oppColorMap[oppId] = _oppColorIdx++;
  }
  return OPP_COLORS[_oppColorMap[oppId] % OPP_COLORS.length];
}

/** Reset the color map (useful if re-rendering). */
function resetColors() {
  _oppColorMap = {};
  _oppColorIdx = 0;
}

/** Format a number with comma separators. */
function fmtNum(n) {
  if (n == null) return '0';
  return Number(n).toLocaleString('en-US');
}

/** Format a dollar amount. */
function fmtUSD(n) {
  if (n == null) return '$0';
  return (
    '$' +
    Number(n).toLocaleString('en-US', {
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    })
  );
}

/** Show an empty-state message inside a container. */
function showEmpty(el, msg) {
  el.innerHTML =
    '<div class="flex items-center justify-center h-full text-gray-400 text-sm">' +
    '<div class="text-center"><i class="fa-solid fa-chart-simple text-3xl mb-2 block"></i>' +
    msg +
    '</div></div>';
}

// ---------------------------------------------------------------------------
// renderKPIs
// ---------------------------------------------------------------------------

function renderKPIs(visits, payments, container) {
  // Count approved visits
  var approvedCount = 0;
  for (var i = 0; i < visits.length; i++) {
    if (visits[i].status === 'approved') approvedCount++;
  }

  // Sum USD
  var totalUSD = 0;
  for (var i = 0; i < payments.length; i++) {
    totalUSD +=
      (parseFloat(payments[i].usd_flw) || 0) +
      (parseFloat(payments[i].usd_org) || 0);
  }

  // Distinct FLWs
  var flwSet = {};
  for (var i = 0; i < visits.length; i++) {
    if (visits[i].username) flwSet[visits[i].username] = true;
  }
  var flwCount = Object.keys(flwSet).length;

  // Distinct countries (from opp metadata, not visits)
  var countrySet = {};
  var visitsByOpp = groupByOpp(visits);
  var paymentsByOpp = groupByOpp(payments);
  var allOpps = Object.assign({}, visitsByOpp, paymentsByOpp);
  for (var id in allOpps) {
    if (allOpps[id].country) countrySet[allOpps[id].country] = true;
  }
  var countryCount = Object.keys(countrySet).length;

  // Date range
  var dates = [];
  for (var i = 0; i < visits.length; i++) {
    if (visits[i].visit_date) dates.push(new Date(visits[i].visit_date));
  }
  dates.sort(function (a, b) {
    return a - b;
  });
  var rangeStr = '—';
  if (dates.length > 0) {
    var fmt = function (d) {
      return d.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      });
    };
    rangeStr = fmt(dates[0]) + ' — ' + fmt(dates[dates.length - 1]);
  }

  var cards = [
    {
      label: 'Approved Visits',
      value: fmtNum(approvedCount),
      icon: 'fa-check-circle',
      color: 'green',
    },
    {
      label: 'Total Payments',
      value: fmtUSD(totalUSD),
      icon: 'fa-dollar-sign',
      color: 'indigo',
    },
    {
      label: 'Active FLWs',
      value: fmtNum(flwCount),
      icon: 'fa-users',
      color: 'blue',
    },
    {
      label: 'Countries',
      value: fmtNum(countryCount),
      icon: 'fa-globe',
      color: 'amber',
    },
  ];

  var html = '<div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-2">';
  for (var i = 0; i < cards.length; i++) {
    var c = cards[i];
    html +=
      '<div class="bg-white rounded-xl shadow-sm p-5 border border-gray-200">' +
      '<div class="flex items-center gap-3">' +
      '<div class="w-10 h-10 bg-' +
      c.color +
      '-50 rounded-lg flex items-center justify-center">' +
      '<i class="fa-solid ' +
      c.icon +
      ' text-' +
      c.color +
      '-600"></i></div>' +
      '<div><div class="text-xs text-gray-500 uppercase tracking-wider">' +
      c.label +
      '</div>' +
      '<div class="text-xl font-bold text-gray-900">' +
      c.value +
      '</div></div></div></div>';
  }
  html += '</div>';
  html +=
    '<div class="text-xs text-gray-400 text-right mb-4">' + rangeStr + '</div>';

  container.innerHTML = html;
}

// ---------------------------------------------------------------------------
// renderVisitsChart
// ---------------------------------------------------------------------------

function renderVisitsChart(visits) {
  var canvas = document.getElementById('visits-chart');
  if (!canvas) return;
  var wrapper = canvas.parentElement;

  var approved = visits.filter(function (v) {
    return v.status === 'approved';
  });
  if (approved.length === 0) {
    showEmpty(wrapper, 'No visit data available');
    canvas.style.display = 'none';
    return;
  }

  var byOpp = groupByOpp(approved);
  var oppIds = Object.keys(byOpp);

  // Collect all visit dates to determine weeks
  var allDates = approved.map(function (v) {
    return v.visit_date;
  });
  var weeks = uniqueWeeks(allDates);

  // Build datasets
  var datasets = [];
  for (var idx = 0; idx < oppIds.length; idx++) {
    var id = oppIds[idx];
    var opp = byOpp[id];
    var color = oppColor(id);

    // Count visits per week
    var weekCounts = {};
    for (var j = 0; j < opp.rows.length; j++) {
      var ws = weekStart(opp.rows[j].visit_date);
      if (ws) weekCounts[ws] = (weekCounts[ws] || 0) + 1;
    }

    var data = weeks.map(function (w) {
      return weekCounts[w] || 0;
    });
    datasets.push({
      label: opp.opp_name,
      data: data,
      backgroundColor: color,
      borderColor: color,
      borderWidth: 1,
    });
  }

  new Chart(canvas, {
    type: 'bar',
    data: {
      labels: weeks,
      datasets: datasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        title: {
          display: true,
          text: 'Approved Visits by Week',
          font: { size: 14 },
        },
        legend: { position: 'bottom', labels: { boxWidth: 12, padding: 12 } },
        tooltip: {
          callbacks: {
            title: function (items) {
              return 'Week of ' + items[0].label;
            },
          },
        },
      },
      scales: {
        x: {
          stacked: true,
          title: { display: true, text: 'Week' },
          ticks: {
            maxRotation: 45,
            callback: function (val, idx) {
              var label = this.getLabelForValue(val);
              // Show abbreviated date
              var d = new Date(label + 'T00:00:00');
              if (isNaN(d.getTime())) return label;
              return d.toLocaleDateString('en-US', {
                month: 'short',
                day: 'numeric',
              });
            },
          },
        },
        y: {
          stacked: true,
          beginAtZero: true,
          title: { display: true, text: 'Visits' },
          ticks: { precision: 0 },
        },
      },
    },
  });
}

// ---------------------------------------------------------------------------
// renderPaymentsChart
// ---------------------------------------------------------------------------

function renderPaymentsChart(payments) {
  var canvas = document.getElementById('payments-chart');
  if (!canvas) return;
  var wrapper = canvas.parentElement;

  if (payments.length === 0) {
    showEmpty(wrapper, 'No payment data available');
    canvas.style.display = 'none';
    return;
  }

  var byOpp = groupByOpp(payments);
  var oppIds = Object.keys(byOpp);

  // Use status_modified_date or payment_date
  var allDates = payments
    .map(function (p) {
      return p.status_modified_date || p.payment_date;
    })
    .filter(Boolean);
  var weeks = uniqueWeeks(allDates);

  var datasets = [];
  for (var idx = 0; idx < oppIds.length; idx++) {
    var id = oppIds[idx];
    var opp = byOpp[id];
    var color = oppColor(id);

    // Sum per week
    var weekSums = {};
    for (var j = 0; j < opp.rows.length; j++) {
      var dateStr =
        opp.rows[j].status_modified_date || opp.rows[j].payment_date;
      var ws = weekStart(dateStr);
      if (ws) {
        var amt =
          (parseFloat(opp.rows[j].usd_flw) || 0) +
          (parseFloat(opp.rows[j].usd_org) || 0);
        weekSums[ws] = (weekSums[ws] || 0) + amt;
      }
    }

    // Cumulative
    var cumulative = [];
    var running = 0;
    for (var w = 0; w < weeks.length; w++) {
      running += weekSums[weeks[w]] || 0;
      cumulative.push(Math.round(running));
    }

    datasets.push({
      label: opp.opp_name,
      data: cumulative,
      borderColor: color,
      backgroundColor: color + '20', // 12% opacity
      fill: true,
      tension: 0.3,
      pointRadius: 2,
      pointHoverRadius: 5,
    });
  }

  new Chart(canvas, {
    type: 'line',
    data: {
      labels: weeks,
      datasets: datasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        title: {
          display: true,
          text: 'Cumulative Payments (USD)',
          font: { size: 14 },
        },
        legend: { position: 'bottom', labels: { boxWidth: 12, padding: 12 } },
        tooltip: {
          callbacks: {
            label: function (ctx) {
              return ctx.dataset.label + ': $' + fmtNum(ctx.raw);
            },
          },
        },
      },
      scales: {
        x: {
          title: { display: true, text: 'Week' },
          ticks: {
            maxRotation: 45,
            callback: function (val, idx) {
              var label = this.getLabelForValue(val);
              var d = new Date(label + 'T00:00:00');
              if (isNaN(d.getTime())) return label;
              return d.toLocaleDateString('en-US', {
                month: 'short',
                day: 'numeric',
              });
            },
          },
        },
        y: {
          beginAtZero: true,
          title: { display: true, text: 'USD' },
          ticks: {
            callback: function (val) {
              return '$' + fmtNum(val);
            },
          },
        },
      },
    },
  });
}

// ---------------------------------------------------------------------------
// renderMap
// ---------------------------------------------------------------------------

function renderMap(visits) {
  var mapDiv = document.getElementById('visits-map');
  if (!mapDiv) return;
  var wrapper = mapDiv.parentElement;

  // Filter to rows with valid locations
  var located = [];
  for (var i = 0; i < visits.length; i++) {
    var loc = visits[i].location;
    if (!loc || typeof loc !== 'string') continue;
    var parts = loc.trim().split(/\s+/);
    if (parts.length < 2) continue;
    var lat = parseFloat(parts[0]);
    var lon = parseFloat(parts[1]);
    if (isNaN(lat) || isNaN(lon) || (lat === 0 && lon === 0)) continue;
    located.push({ row: visits[i], lat: lat, lon: lon });
  }

  if (located.length === 0) {
    showEmpty(wrapper, 'No location data available');
    mapDiv.style.display = 'none';
    return;
  }

  // Initialize map
  var map = L.map(mapDiv).setView([0, 0], 2);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution:
      '&copy; <a href="https://openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 18,
  }).addTo(map);

  // Marker cluster with fallback
  var clusterGroup;
  if (typeof L.markerClusterGroup === 'function') {
    clusterGroup = L.markerClusterGroup({ maxClusterRadius: 40 });
  } else {
    clusterGroup = L.layerGroup();
  }

  var bounds = [];
  for (var i = 0; i < located.length; i++) {
    var pt = located[i];
    var color = oppColor(String(pt.row.opp_id));
    var marker = L.circleMarker([pt.lat, pt.lon], {
      radius: 5,
      fillColor: color,
      color: color,
      weight: 1,
      opacity: 0.8,
      fillOpacity: 0.6,
    });

    var visitDate = pt.row.visit_date
      ? new Date(pt.row.visit_date).toLocaleDateString()
      : '';
    marker.bindPopup(
      '<div class="text-sm">' +
        '<div class="font-medium">' +
        (pt.row.entity_name || 'Unknown') +
        '</div>' +
        '<div class="text-gray-500">' +
        (pt.row.opp_name || '') +
        '</div>' +
        (visitDate
          ? '<div class="text-gray-400 text-xs">' + visitDate + '</div>'
          : '') +
        '</div>',
    );

    clusterGroup.addLayer(marker);
    bounds.push([pt.lat, pt.lon]);
  }

  clusterGroup.addTo(map);

  if (bounds.length > 0) {
    map.fitBounds(bounds, { padding: [30, 30], maxZoom: 12 });
  }

  // Fix Leaflet map rendering in hidden containers
  setTimeout(function () {
    map.invalidateSize();
  }, 100);
}
