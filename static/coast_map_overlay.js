/* Coast trajectory overlay for Rocket Planner ground track.
 * Loaded after app.js; redefines map drawing to include the coast arc.
 */
(function () {
  if (typeof splitTrack !== "function") return;

  function renderGroundTrackFallback(el, asc, coast, orb, p) {
    const W = 960, H = 480;
    const project = (pt) => [
      ((Number(pt[1]) + 180) / 360) * W,
      ((90 - Math.max(-90, Math.min(90, Number(pt[0])))) / 180) * H,
    ];
    const path = (points) =>
      splitTrack(points)
        .map((seg) =>
          seg
            .map((pt, i) => {
              const q = project(pt);
              return (i ? "L" : "M") + q[0].toFixed(1) + "," + q[1].toFixed(1);
            })
            .join(" ")
        )
        .join(" ");
    let grid = "";
    for (let lon = -180; lon <= 180; lon += 30) {
      const x = ((lon + 180) / 360) * W;
      grid +=
        '<line x1="' +
        x +
        '" y1="0" x2="' +
        x +
        '" y2="' +
        H +
        '" stroke="#26384d"/><text x="' +
        x +
        '" y="18" fill="#9fb2c5" font-size="12" text-anchor="middle">' +
        lon +
        "°</text>";
    }
    for (let lat = -60; lat <= 60; lat += 30) {
      const y = ((90 - lat) / 180) * H;
      grid +=
        '<line x1="0" y1="' +
        y +
        '" x2="' +
        W +
        '" y2="' +
        y +
        '" stroke="#26384d"/><text x="8" y="' +
        (y - 5) +
        '" fill="#9fb2c5" font-size="12">' +
        lat +
        "°</text>";
    }
    const launch = project([p.site_lat, p.site_lon]);
    const observer = project([p.obs_lat, p.obs_lon]);
    el.innerHTML =
      '<svg viewBox="0 0 ' +
      W +
      " " +
      H +
      '" role="img" aria-label="Ground track" style="width:100%;height:100%;min-height:260px;display:block;background:#091523">' +
      grid +
      '<path d="' +
      path(asc) +
      '" fill="none" stroke="#ff8b59" stroke-width="3" stroke-linejoin="round"/>' +
      '<path d="' +
      path(coast) +
      '" fill="none" stroke="#f5c76b" stroke-width="2.5" stroke-dasharray="4 4" stroke-linejoin="round"/>' +
      '<path d="' +
      path(orb) +
      '" fill="none" stroke="#53d5d0" stroke-width="2.5" stroke-dasharray="7 5" stroke-linejoin="round"/>' +
      '<circle cx="' +
      launch[0] +
      '" cy="' +
      launch[1] +
      '" r="6" fill="#f5c76b"/><circle cx="' +
      observer[0] +
      '" cy="' +
      observer[1] +
      '" r="6" fill="#ffffff"/>' +
      '<text x="18" y="' +
      (H - 18) +
      '" fill="#9fb2c5" font-size="13">Ascent · Coast · Orbit</text></svg>';
  }

  window.drawMap = function drawMap(data, p) {
    const el = document.getElementById("map");
    if (!el) return;
    const ascent = Array.isArray(data.ascent) ? data.ascent : [];
    const coastRows = Array.isArray(data.coast) ? data.coast : [];
    const orbit = Array.isArray(data.orbit) ? data.orbit : [];
    const asc = ascent
      .filter((x) => Number.isFinite(Number(x.lat)) && Number.isFinite(Number(x.lon)))
      .map((x) => [Number(x.lat), Number(x.lon)]);
    const coast = coastRows
      .filter((x) => Number.isFinite(Number(x.lat)) && Number.isFinite(Number(x.lon)))
      .map((x) => [Number(x.lat), Number(x.lon)]);
    const orb = orbit
      .filter((x) => Number.isFinite(Number(x.lat)) && Number.isFinite(Number(x.lon)))
      .map((x) => [Number(x.lat), Number(x.lon)]);
    if (!asc.length && !coast.length && !orb.length) {
      el.innerHTML = '<p class="hint">ไม่มีพิกัดเส้นทางสำหรับแสดงแผนที่</p>';
      return;
    }
    try {
      if (window.mapObj) {
        try { window.mapObj.remove(); } catch (_) {}
        window.mapObj = null;
      }
      if (!window.L || typeof L.map !== "function") {
        renderGroundTrackFallback(el, asc, coast, orb, p);
        return;
      }
      window.mapObj = L.map(el, { worldCopyJump: true }).setView([0, 0], 2);
      const tiles = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "© OpenStreetMap",
        maxZoom: 18,
      });
      let tileErrors = 0;
      tiles.on("tileerror", () => {
        tileErrors++;
        if (tileErrors >= 3 && window.mapObj) {
          try { window.mapObj.remove(); } catch (_) {}
          window.mapObj = null;
          renderGroundTrackFallback(el, asc, coast, orb, p);
        }
      });
      tiles.addTo(window.mapObj);
      splitTrack(asc).forEach((seg) =>
        L.polyline(seg, { color: "#ff8b59", weight: 3, opacity: 0.95 })
          .addTo(window.mapObj)
          .bindPopup("Ascent")
      );
      splitTrack(coast).forEach((seg) =>
        L.polyline(seg, { color: "#f5c76b", weight: 2.5, dashArray: "4 4", opacity: 0.95 })
          .addTo(window.mapObj)
          .bindPopup("Coast")
      );
      splitTrack(orb).forEach((seg) =>
        L.polyline(seg, { color: "#53d5d0", weight: 2, dashArray: "6 5", opacity: 0.9 })
          .addTo(window.mapObj)
          .bindPopup("Orbit")
      );
      if (Number.isFinite(Number(p.site_lat)) && Number.isFinite(Number(p.site_lon)))
        L.marker([p.site_lat, p.site_lon]).addTo(window.mapObj).bindPopup("Launch site");
      if (Number.isFinite(Number(p.obs_lat)) && Number.isFinite(Number(p.obs_lon)))
        L.marker([p.obs_lat, p.obs_lon]).addTo(window.mapObj).bindPopup("Observer");
      requestAnimationFrame(() => {
        if (!window.mapObj) return;
        window.mapObj.invalidateSize();
        const frame = asc.concat(coast);
        if (frame.length > 1) {
          const bounds = L.latLngBounds(frame);
          if (bounds.isValid())
            window.mapObj.fitBounds(bounds.pad(0.12), { padding: [24, 24], maxZoom: 5 });
        } else if (asc.length > 1) {
          const bounds = L.latLngBounds(asc);
          if (bounds.isValid())
            window.mapObj.fitBounds(bounds.pad(0.12), { padding: [24, 24], maxZoom: 4 });
        } else if (Number.isFinite(Number(p.site_lat)) && Number.isFinite(Number(p.site_lon))) {
          window.mapObj.setView([Number(p.site_lat), Number(p.site_lon)], 3);
        } else if (orb.length) {
          window.mapObj.setView(orb[0], 2);
        }
      });
    } catch (err) {
      console.error("Ground track render failed", err);
      if (window.mapObj) {
        try { window.mapObj.remove(); } catch (_) {}
        window.mapObj = null;
      }
      renderGroundTrackFallback(el, asc, coast, orb, p);
    }
  };

  window.buildKml = function (data) {
    const placemark = (name, pts, color) => {
      const lines = splitTrack((pts || []).map((x) => [x.lat, x.lon, x.alt_km * 1000]));
      return lines
        .map(
          (seg) =>
            `<Placemark><name>${name}</name><Style><LineStyle><color>${color}</color><width>3</width></LineStyle></Style><LineString><altitudeMode>absolute</altitudeMode><coordinates>${seg
              .map((x) => x[1].toFixed(6) + "," + x[0].toFixed(6) + "," + x[2].toFixed(1))
              .join(" ")}</coordinates></LineString></Placemark>`
        )
        .join("");
    };
    return (
      '<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>Rocket Planner trajectory</name>' +
      placemark("Ascent", data.ascent, "ff598bff") +
      placemark("Coast", data.coast, "ff6bc7f5") +
      placemark("Orbit", data.orbit, "ffd0d653") +
      "</Document></kml>"
    );
  };
})();
