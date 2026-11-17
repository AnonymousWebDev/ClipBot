/* Clip Bot: manual source-frame crop calibration, no framework or paid vision APIs. */
(function () {
  "use strict";

  const clamp = (n, a, b) => Math.min(b, Math.max(a, n));
  const copyBox = b => b && typeof b === "object" ? {
    x:Number(b.x), y:Number(b.y), w:Number(b.w), h:Number(b.h)
  } : null;

  function mount(container, creator, onSave) {
    if (!container) return;
    const values = {facecam:copyBox(creator.facecam_box), gameplay:copyBox(creator.gameplay_box)};
    let mode = "facecam", imageLoaded = false, action = null;
    container.innerHTML = [
      '<div class="card"><h2>Webcam layout editor</h2>',
      '<p class="help">Draw around the streamer webcam. Optionally select a gameplay region. ',
      'Drag an existing box to move it or its lower-right handle to resize. ',
      'The original video remains unchanged.</p>',
      '<div class="cb-grid"><div>',
      '<div class="cb-tools">',
      '<button type="button" class="btn sm primary" data-mode="facecam">Select webcam</button>',
      '<button type="button" class="btn sm" data-mode="gameplay">Select gameplay</button>',
      '<button type="button" class="btn sm" data-cb-action="frame">Refresh frame</button></div>',
      '<div class="cb-source" role="group" aria-label="Recorded source frame and crop selections">',
      '<img class="cb-frame" alt="Frame captured from a recorded stream" draggable="false">',
      '<div class="cb-boxes"></div></div>',
      '<p class="help cb-message" role="status">Loading a recorded frame…</p>',
      '<div class="cb-tools"><button class="btn sm" type="button" data-cb-action="clear">Clear selected region</button></div>',
      '</div><div class="cb-right"><div class="cb-prev-label">Vertical clip preview</div>',
      '<canvas class="cb-preview" width="360" height="640" aria-label="Approximate 9:16 stacked layout preview"></canvas>',
      '<p class="help">Full webcam on top, gameplay below. Empty space uses a soft background in the final render.</p>',
      '</div></div>',
      '<div class="cb-footer"><span class="help">This saves a preset for future clips. Automatic posting remains disabled until layout validation is built.</span>',
      '<button type="button" class="btn primary" data-cb-action="save">Save layout</button></div></div>'
    ].join("");

    const img = container.querySelector(".cb-frame");
    const source = container.querySelector(".cb-source");
    const boxes = container.querySelector(".cb-boxes");
    const preview = container.querySelector(".cb-preview");
    const message = container.querySelector(".cb-message");
    const saveButton = container.querySelector('[data-cb-action="save"]');
    const context = preview.getContext("2d");

    function buttons() {
      container.querySelectorAll("[data-mode]").forEach(b => {
        b.classList.toggle("primary", b.dataset.mode === mode);
      });
    }
    function selectionMarkup(which, box) {
      if (!box) return "";
      const el = document.createElement("div");
      el.className = "cb-select cb-" + which;
      el.dataset.which = which;
      el.style.left = (box.x * 100) + "%";
      el.style.top = (box.y * 100) + "%";
      el.style.width = (box.w * 100) + "%";
      el.style.height = (box.h * 100) + "%";
      el.innerHTML = '<span>' + (which === "facecam" ? "Webcam" : "Gameplay") +
        '</span><i class="cb-handle" aria-hidden="true"></i>';
      return el;
    }
    function drawPart(box, destX, destY, destW, destH) {
      if (!imageLoaded || !box) return;
      const sx = img.naturalWidth * box.x, sy = img.naturalHeight * box.y;
      const sw = img.naturalWidth * box.w, sh = img.naturalHeight * box.h;
      if (sw < 1 || sh < 1) return;
      const scale = Math.min(destW / sw, destH / sh);
      const w = sw * scale, h = sh * scale;
      context.drawImage(img, sx, sy, sw, sh,
        destX + (destW - w) / 2, destY + (destH - h) / 2, w, h);
    }
    function draw() {
      boxes.replaceChildren();
      ["facecam", "gameplay"].forEach(which => {
        const el = selectionMarkup(which, values[which]);
        if (el) boxes.appendChild(el);
      });
      context.clearRect(0, 0, 360, 640);
      context.fillStyle = "#20232c";
      context.fillRect(0, 0, 360, 640);
      if (imageLoaded) {
        context.save();
        context.filter = "blur(12px) brightness(0.58)";
        context.drawImage(img, 0, 0, 360, 640);
        context.restore();
      }
      drawPart(values.facecam, 0, 0, 360, 173);
      drawPart(values.gameplay || {x:0, y:0, w:1, h:1}, 0, 173, 360, 467);
      context.fillStyle = "rgba(255,255,255,.8)";
      context.font = "14px sans-serif";
      if (!values.facecam) context.fillText("Draw webcam box on the left", 18, 82);
      context.fillText("GAMEPLAY", 12, 626);
    }
    function normalizedPoint(event) {
      const r = source.getBoundingClientRect();
      return {x:clamp((event.clientX - r.left) / r.width, 0, 1),
              y:clamp((event.clientY - r.top) / r.height, 0, 1)};
    }
    source.addEventListener("pointerdown", e => {
      if (!imageLoaded || e.button !== 0) return;
      const p = normalizedPoint(e), selected = e.target.closest(".cb-select");
      if (selected) {
        mode = selected.dataset.which;
        action = {kind:e.target.closest(".cb-handle") ? "resize" : "move",
                  which:mode, start:p, original:{...values[mode]}};
      } else {
        action = {kind:"draw", which:mode, start:p, original:values[mode]};
        values[mode] = {x:p.x, y:p.y, w:.03, h:.03};
      }
      buttons(); source.setPointerCapture(e.pointerId); e.preventDefault(); draw();
    });
    source.addEventListener("pointermove", e => {
      if (!action) return;
      const p = normalizedPoint(e), a = action;
      if (a.kind === "draw") {
        values[a.which] = {
          x:Math.min(a.start.x, p.x), y:Math.min(a.start.y, p.y),
          w:Math.abs(p.x-a.start.x), h:Math.abs(p.y-a.start.y)
        };
      } else if (a.kind === "move") {
        values[a.which] = {...a.original,
          x:clamp(a.original.x+p.x-a.start.x, 0, 1-a.original.w),
          y:clamp(a.original.y+p.y-a.start.y, 0, 1-a.original.h)};
      } else {
        values[a.which] = {...a.original,
          w:clamp(a.original.w+p.x-a.start.x, .03, 1-a.original.x),
          h:clamp(a.original.h+p.y-a.start.y, .03, 1-a.original.y)};
      }
      draw();
    });
    function finishPointer() {
      if (!action) return;
      const b = values[action.which];
      if (b && (b.w < .03 || b.h < .03)) values[action.which] = action.original;
      action = null; draw();
    }
    source.addEventListener("pointerup", finishPointer);
    source.addEventListener("pointercancel", finishPointer);
    container.querySelectorAll("[data-mode]").forEach(b => b.addEventListener("click", () => {
      mode = b.dataset.mode; buttons(); draw();
    }));
    container.querySelector('[data-cb-action="clear"]').addEventListener("click", () => {
      values[mode] = null; draw();
    });
    function refresh() {
      imageLoaded = false;
      message.textContent = "Loading a recorded frame…";
      img.style.visibility = "hidden";
      img.src = "/api/creators/" + encodeURIComponent(creator.id) +
        "/layout/frame?fresh=" + Date.now();
    }
    img.onload = () => {
      imageLoaded = true;
      source.style.aspectRatio = img.naturalWidth + " / " + img.naturalHeight;
      img.style.visibility = "visible";
      message.textContent = "Frame loaded · " + img.naturalWidth + " × " +
        img.naturalHeight + " · drag to select a region.";
      draw();
    };
    img.onerror = () => {
      imageLoaded = false;
      message.textContent = "No saved stream frame yet. Record this streamer or make a clip, then refresh.";
      draw();
    };
    container.querySelector('[data-cb-action="frame"]').addEventListener("click", refresh);
    saveButton.addEventListener("click", async () => {
      if (!values.facecam || values.facecam.w < .03 || values.facecam.h < .03) {
        message.textContent = "Select the webcam before saving.";
        return;
      }
      saveButton.disabled = true;
      try {
        const rounded = b => b && Object.fromEntries(
          Object.entries(b).map(([k,v]) => [k, Number(v.toFixed(6))]));
        await onSave({facecam_box:rounded(values.facecam),
          gameplay_box:rounded(values.gameplay), layout:"facecam_top"});
        message.textContent = "Layout preset saved. New clips will use it.";
      } catch (e) {
        message.textContent = "Could not save layout: " + e.message;
      } finally {
        saveButton.disabled = false;
      }
    });
    buttons(); draw(); refresh();
  }

  window.ClipBotLayout = {mount};
}());
