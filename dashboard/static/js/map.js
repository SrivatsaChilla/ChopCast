/* Offline-first Leaflet map. No external requests unless a tile URL is configured. */
(function () {
  "use strict";

  function heuristic(raw) {
    var text = String(raw || "").toUpperCase();
    if (text.indexOf("SEV") !== -1) return "Severe";
    if (text.indexOf("MOD") !== -1 || text.indexOf("CHOP") !== -1) return "Moderate";
    if (text.indexOf("LGT") !== -1 || text.indexOf("LIGHT") !== -1) return "Light";
    if (text.indexOf("NEG") !== -1 || text.indexOf("NONE") !== -1 || text.indexOf("NIL") !== -1) return "None";
    return "Unlabelled";
  }

  function labelFor(props, layer) {
    var raw;
    if (layer === "primary") raw = props.label_primary;
    else if (layer === "secondary") raw = props.label_secondary;
    else raw = props.label_combined;
    if (!raw) return "Unlabelled";
    return config.raw_labels[raw] || heuristic(raw);
  }

  var config = null;

  window.addEventListener("DOMContentLoaded", function () {
    var node = document.getElementById("map");
    var configNode = document.getElementById("map-config");
    if (!node || !configNode || typeof window.L === "undefined") return;
    try { config = JSON.parse(configNode.textContent); } catch (e) { return; }

    var map = window.L.map(node, { minZoom: 2, worldCopyJump: true }).setView([25, 0], 2);
    window.L.control.scale({ imperial: false }).addTo(map);

    if (config.tile_url) {
      window.L.tileLayer(config.tile_url, {
        maxZoom: 18,
        attribution: "Configured tile source"
      }).addTo(map);
    }

    fetch(config.world_url)
      .then(function (response) { return response.ok ? response.json() : null; })
      .then(function (world) {
        if (!world) return;
        window.L.geoJSON(world, {
          style: { color: "#b8c2cc", weight: 0.5, fillColor: "#dfe5ea", fillOpacity: 1 }
        }).addTo(map);
      })
      .catch(function () { /* the map still works without the outline */ });

    var markers = window.L.layerGroup().addTo(map);
    var heat = null;
    var points = [];
    var layerName = "combined";
    var status = document.getElementById("map-status");

    function markerGroup() {
      var clustered = document.getElementById("show-clusters");
      if (clustered && clustered.checked && points.length > 500 && window.L.markerClusterGroup) {
        return window.L.markerClusterGroup({ showCoverageOnHover: false, maxClusterRadius: 45 });
      }
      return window.L.layerGroup();
    }

    function popup(feature) {
      var props = feature.properties || {};
      var wrap = document.createElement("div");
      var title = document.createElement("div");
      title.className = "popup-title";
      var link = document.createElement("a");
      link.href = "/data/reports/" + encodeURIComponent(props.hash || "");
      link.textContent = (props.hash || "").slice(0, 12) + "…";
      title.appendChild(link);
      wrap.appendChild(title);

      var meta = document.createElement("div");
      meta.className = "popup-meta";
      meta.textContent = [props.obs_time, props.altitude ? props.altitude + " ft" : null,
        props.aircraft, props.report_type].filter(Boolean).join(" · ");
      wrap.appendChild(meta);

      var labels = document.createElement("div");
      labels.className = "popup-meta";
      var cls = labelFor(props, layerName);
      labels.textContent = "Class: " + cls +
        (props.label_primary ? " · primary " + props.label_primary : "") +
        (props.label_secondary ? " · secondary " + props.label_secondary : "") +
        (props.suspicious ? " · suspicious 0,0" : "");
      wrap.appendChild(labels);

      if (props.raw_text) {
        var text = document.createElement("div");
        text.className = "popup-text";
        text.textContent = props.raw_text;
        wrap.appendChild(text);
      }
      return wrap;
    }

    function render() {
      if (markers) map.removeLayer(markers);
      var group = markerGroup();
      points.forEach(function (feature) {
        var coords = feature.geometry.coordinates;
        var props = feature.properties || {};
        var cls = labelFor(props, layerName);
        var color = config.colors[cls] || config.colors.Unlabelled;
        var options = {
          radius: 6,
          color: color,
          weight: 1,
          fillColor: color,
          fillOpacity: 0.78
        };
        if (props.suspicious) options.dashArray = "3 3";
        group.addLayer(window.L.circleMarker([coords[1], coords[0]], options).bindPopup(popup(feature)));
      });
      group.addTo(map);
      markers = group;
      var show = document.getElementById("show-markers");
      if (show && !show.checked) map.removeLayer(markers);

      if (heat) {
        map.removeLayer(heat);
        heat = null;
      }
      var heatToggle = document.getElementById("show-heat");
      if (heatToggle && heatToggle.checked && window.L.heatLayer) {
        heat = window.L.heatLayer(points.map(function (feature) {
          return [feature.geometry.coordinates[1], feature.geometry.coordinates[0], 0.65];
        }), { radius: 20, blur: 22, maxZoom: 9 });
        heat.addTo(map);
      }
    }

    function updateStatus(meta) {
      if (!status) return;
      var parts = [];
      if (meta.plottable !== undefined) parts.push(meta.plottable + " plottable");
      if (meta.returned !== undefined) parts.push(meta.returned + " plotted");
      if (meta.truncated) parts.push("truncated at " + meta.max_points);
      if (meta.invalid_coords) parts.push(meta.invalid_coords + " invalid coordinates omitted");
      status.textContent = parts.join(" · ");
    }

    fetch(config.data_url, { headers: { "Accept": "application/json" } })
      .then(function (response) {
        if (!response.ok) throw new Error("HTTP " + response.status);
        return response.json();
      })
      .then(function (data) {
        points = (data.features || []).slice(0, config.max_points || points.length);
        layerName = (data.meta && data.meta.filters && data.meta.filters.label_layer) || "combined";
        render();
        updateStatus(data.meta || {});
        if (points.length) {
          var bounds = window.L.latLngBounds(points.map(function (feature) {
            return [feature.geometry.coordinates[1], feature.geometry.coordinates[0]];
          }));
          map.fitBounds(bounds.pad(0.15), { maxZoom: 7 });
        }
      })
      .catch(function (error) {
        if (status) status.textContent = "Could not load map points: " + error.message;
      });

    document.querySelectorAll("#show-markers, #show-clusters, #show-heat").forEach(function (input) {
      input.addEventListener("change", render);
    });

    var filterButton = document.getElementById("filter-view");
    var form = document.getElementById("map-filters");
    if (filterButton && form) {
      filterButton.addEventListener("click", function () {
        var bounds = map.getBounds();
        var input = form.querySelector("input[name='bbox']");
        if (!input) {
          input = document.createElement("input");
          input.type = "hidden";
          input.name = "bbox";
          form.appendChild(input);
        }
        input.value = [bounds.getSouth(), bounds.getWest(), bounds.getNorth(), bounds.getEast()]
          .map(function (value) { return value.toFixed(4); }).join(",");
        form.submit();
      });
    }
  });
})();
