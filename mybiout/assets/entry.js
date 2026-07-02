(function () {
    const PINK = "#E85B8A";
    const ORANGE = "#F5A623";
    const BLUE = "#00AEEC";
    const INK = "#2B1822";
    const PAPER = "#FFFFFF";
    const ENTRY_SPEED = 1.3;
    const BASE_TIMING = {
        ready: 780,
        fallbackReady: 920,
        canvas: 1880,
        render: 2300,
        remove: 2450,
        overlayDelay: 1780,
        overlayDuration: 520,
    };

    const ENTRY_VARIANTS = [
        { name: "sticker-pop", mode: "sticker", family: "manga", colors: [PINK, ORANGE, BLUE, PAPER] },
        { name: "card-slam", mode: "cards", family: "wipe", colors: [BLUE, PAPER, PINK, ORANGE] },
        { name: "manga-burst", mode: "burst", family: "manga", colors: [ORANGE, PINK, PAPER, BLUE] },
        { name: "confetti-cannon", mode: "confetti", family: "manga", colors: [PINK, ORANGE, BLUE, PAPER] },
        { name: "wave-ribbons", mode: "waves", family: "soft", colors: [BLUE, PINK, ORANGE, PAPER] },
        { name: "checker-wipe", mode: "checker", family: "wipe", colors: [PINK, PAPER, BLUE, ORANGE] },
        { name: "shutter-cards", mode: "shutters", family: "wipe", colors: [ORANGE, PINK, PAPER, BLUE] },
        { name: "stamp-ripple", mode: "ripples", family: "manga", colors: [PINK, PAPER, ORANGE, BLUE] },
        { name: "paper-fold", mode: "folds", family: "wipe", colors: [PAPER, BLUE, PINK, ORANGE] },
        { name: "scan-bars", mode: "bars", family: "wipe", colors: [BLUE, PAPER, PINK, ORANGE] },
        { name: "dot-matrix", mode: "dots", family: "soft", colors: [PINK, ORANGE, BLUE, PAPER] },
        { name: "carousel-slices", mode: "slices", family: "manga", colors: [BLUE, ORANGE, PINK, PAPER] },
        { name: "ribbon-weave", mode: "weave", family: "soft", colors: [ORANGE, BLUE, PINK, PAPER] },
        { name: "flash-cards", mode: "flash", family: "wipe", colors: [PAPER, PINK, BLUE, ORANGE] },
        { name: "bubble-splash", mode: "bubbles", family: "soft", colors: [BLUE, PINK, ORANGE, PAPER] },
    ];

    window.MYBIOUT_ENTRY_VARIANTS = ENTRY_VARIANTS.map((variant) => variant.name);

    const overlay = document.querySelector(".mybiout-entry-overlay");
    if (!overlay) {
        document.body.classList.add("mybiout-entry-ready");
        return;
    }

    const reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduceMotion) {
        overlay.remove();
        document.body.classList.add("mybiout-entry-ready");
        return;
    }

    const variant = ENTRY_VARIANTS[Math.floor(Math.random() * ENTRY_VARIANTS.length)];
    const generated = generateVariant(variant);
    overlay.classList.add(`entry-${variant.name}`);
    overlay.dataset.entryFamily = variant.family;
    overlay.style.setProperty("--entry-overlay-delay", `${speedMs(BASE_TIMING.overlayDelay)}ms`);
    overlay.style.setProperty("--entry-overlay-duration", `${speedMs(BASE_TIMING.overlayDuration)}ms`);
    overlay.style.setProperty("--entry-core-duration", `${speedSec(1250)}s`);

    let canvas = overlay.querySelector(".mybiout-entry-canvas");
    if (!canvas) {
        canvas = document.createElement("canvas");
        canvas.className = "mybiout-entry-canvas";
        overlay.prepend(canvas);
    }

    let stage = overlay.querySelector(".mybiout-entry-stage");
    if (!stage) {
        stage = document.createElement("div");
        stage.className = "mybiout-entry-stage";
        overlay.appendChild(stage);
    }

    let core = overlay.querySelector(".mybiout-entry-core");
    if (!core) {
        core = document.createElement("div");
        core.className = "mybiout-entry-core";
        stage.appendChild(core);
    }

    core.style.setProperty("--entry-core-bg", generated.palette[0]);
    core.style.setProperty("--entry-shadow", generated.palette[2]);
    core.style.setProperty("--entry-tilt", `${generated.angle * 0.08}deg`);

    const ctx = canvas.getContext("2d", { alpha: true });
    const flecks = createFlecks(generated, Math.round(160 * generated.density));
    let width = 0;
    let height = 0;
    let dpr = 1;
    let startedAt = performance.now();
    let readySent = false;

    function resize() {
        dpr = Math.min(window.devicePixelRatio || 1, 2);
        width = Math.max(1, window.innerWidth);
        height = Math.max(1, window.innerHeight);
        canvas.width = Math.floor(width * dpr);
        canvas.height = Math.floor(height * dpr);
        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    resize();
    buildPieces(overlay, variant, generated);
    window.addEventListener("resize", resize, { passive: true });
    requestAnimationFrame(render);

    window.setTimeout(() => {
        document.body.classList.add("mybiout-entry-ready");
    }, speedMs(BASE_TIMING.fallbackReady));

    window.setTimeout(() => {
        window.removeEventListener("resize", resize);
        overlay.remove();
    }, speedMs(BASE_TIMING.remove));

    function render(now) {
        const elapsed = now - startedAt;
        const t = Math.min(elapsed / speedMs(BASE_TIMING.canvas), 1);
        const e = easeOutCubic(t);

        ctx.clearRect(0, 0, width, height);
        drawPaper(ctx, generated, width, height, t);
        drawMode(ctx, generated, width, height, t, e, elapsed * 0.001 * ENTRY_SPEED);
        drawFlecks(ctx, flecks, width, height, t, elapsed * 0.001);

        if (!readySent && elapsed > speedMs(BASE_TIMING.ready)) {
            readySent = true;
            document.body.classList.add("mybiout-entry-ready");
        }

        if (elapsed < speedMs(BASE_TIMING.render) && overlay.isConnected) {
            requestAnimationFrame(render);
        }
    }

    function buildPieces(root, variant, generated) {
        const base = {
            sticker: [34, "dot"],
            cards: [18, "card"],
            burst: [42, "line"],
            confetti: [70, "slice"],
            waves: [22, "line"],
            checker: [44, "card"],
            shutters: [16, "card"],
            ripples: [24, "dot"],
            folds: [22, "triangle"],
            bars: [26, "line"],
            dots: [96, "dot"],
            slices: [28, "slice"],
            weave: [34, "line"],
            flash: [20, "card"],
            bubbles: [46, "dot"],
        }[variant.mode] || [32, "slice"];
        const count = Math.max(8, Math.round(base[0] * generated.density));

        for (let i = 0; i < count; i++) {
            const type = choosePieceType(base[1], i, variant.mode);
            const piece = document.createElement("i");
            piece.className = `mybiout-entry-piece ${type}`;
            const size = pieceSize(type, i, variant.mode, generated);
            const color = generated.palette[i % generated.palette.length];
            piece.style.left = `${rand(-8, 100)}vw`;
            piece.style.top = `${rand(-8, 100)}vh`;
            piece.style.width = `${size.w}px`;
            piece.style.height = `${size.h}px`;
            piece.style.setProperty("--piece-fill", color);
            piece.style.setProperty("--piece-ink", type === "triangle" ? "transparent" : INK);
            piece.style.setProperty("--piece-shadow", alpha(INK, 0.18));
            root.appendChild(piece);
            animatePiece(piece, i, variant.mode, generated);
        }
    }

    function choosePieceType(type, index, mode) {
        if (mode === "confetti") {
            return ["slice", "dot", "card", "triangle"][index % 4];
        }
        if (mode === "flash") {
            return index % 3 === 0 ? "line" : "card";
        }
        if (mode === "sticker") {
            return index % 4 === 0 ? "card" : "dot";
        }
        return type;
    }

    function pieceSize(type, index, mode, generated) {
        const sizeJitter = generated.size;
        if (type === "line") {
            return { w: rand(90, mode === "burst" ? 390 : 260) * sizeJitter, h: rand(5, 14) * sizeJitter };
        }
        if (type === "dot") {
            const d = rand(mode === "dots" ? 5 : 12, mode === "bubbles" ? 84 : 42) * sizeJitter;
            return { w: d, h: d };
        }
        if (type === "triangle") {
            const d = rand(38, 120) * sizeJitter;
            return { w: d, h: d * rand(0.72, 1.22) };
        }
        if (type === "slice") {
            return { w: rand(34, 120) * sizeJitter, h: rand(26, 92) * sizeJitter };
        }
        const side = (mode === "checker" ? rand(34, 70) : rand(64, 170)) * sizeJitter;
        return { w: side * rand(0.8, 1.55), h: side };
    }

    function animatePiece(piece, index, mode, generated) {
        const a = generated.angleRad + rand(0, Math.PI * 2);
        const span = Math.max(window.innerWidth, window.innerHeight);
        const spread = generated.spread;
        const startX = mode === "shutters" ? (index % 2 ? -span : span) : Math.cos(a) * rand(120, span * 0.45) * spread;
        const startY = mode === "bars" ? rand(-span * 0.3, span * 0.3) * spread : Math.sin(a) * rand(80, span * 0.36) * spread;
        const endX = mode === "checker" ? 0 : Math.cos(a + Math.PI) * rand(30, span * 0.18) * spread;
        const endY = mode === "checker" ? 0 : Math.sin(a + Math.PI) * rand(30, span * 0.14) * spread;
        const rotA = generated.angle * 0.3 + rand(-34, 34);
        const rotB = rotA + rand(60, 260) * (index % 2 ? -1 : 1) * generated.rotation;
        const delay = speedMs(rand(0, mode === "flash" ? 180 : 420));
        const duration = speedMs(rand(920, mode === "bubbles" ? 1720 : 1380) * generated.pace);

        piece.animate(
            [
                {
                    opacity: 0,
                    transform: `translate(${startX}px, ${startY}px) rotate(${rotA}deg) scale(.35)`,
                },
                {
                    opacity: mode === "flash" ? .72 : .96,
                    transform: `translate(0, 0) rotate(${rotB * .26}deg) scale(1)`,
                    offset: mode === "checker" ? .34 : .52,
                },
                {
                    opacity: 0,
                    transform: `translate(${endX}px, ${endY}px) rotate(${rotB}deg) scale(${mode === "dots" ? 1.4 : .86})`,
                },
            ],
            {
                delay,
                duration,
                easing: "cubic-bezier(.18,.86,.22,1)",
                fill: "both",
            },
        );
    }

    function drawPaper(c, variant, w, h, t) {
        const wash = c.createLinearGradient(0, 0, w, h);
        wash.addColorStop(0, "#FFFFFF");
        wash.addColorStop(0.5, tint(variant.colors[0], 0.9));
        wash.addColorStop(1, tint(variant.colors[2], 0.9));
        c.fillStyle = wash;
        c.fillRect(0, 0, w, h);

        c.globalAlpha = 0.18;
        c.fillStyle = variant.colors[0];
        const step = variant.grid.cell;
        if (variant.algorithm === "diagonal") {
            c.save();
            c.rotate(variant.angleRad * 0.25);
            for (let y = -h; y < h * 1.6; y += step * 1.4) {
                c.fillRect(-w * 0.2, y, w * 1.4, 4 + variant.dot);
            }
            c.restore();
        } else if (variant.algorithm === "fold") {
            for (let x = -step; x < w + step; x += step * 2.2) {
                c.fillRect(x, 0, step * 0.22, h);
            }
            for (let y = -step; y < h + step; y += step * 2.2) {
                c.fillRect(0, y, w, step * 0.18);
            }
        } else {
            for (let y = -step; y < h + step; y += step) {
                for (let x = -step; x < w + step; x += step) {
                    const radialGate = variant.algorithm === "radial"
                        ? Math.sin(Math.hypot(x - w / 2, y - h / 2) * 0.025 + variant.phase) > -0.28
                        : true;
                    if (radialGate && (Math.floor(x / step) + Math.floor(y / step)) % 2 === 0) {
                        c.beginPath();
                        c.arc(x + step * 0.3, y + step * 0.3, 1.4 + Math.sin(t * Math.PI) * variant.dot, 0, Math.PI * 2);
                        c.fill();
                    }
                }
            }
        }
        c.globalAlpha = 1;
    }

    function drawMode(c, variant, w, h, t, e, seconds) {
        switch (variant.mode) {
            case "sticker":
                drawSticker(c, variant, w, h, e, seconds);
                break;
            case "cards":
                drawCards(c, variant, w, h, e);
                break;
            case "burst":
                drawBurst(c, variant, w, h, e, seconds);
                break;
            case "confetti":
                drawConfetti(c, variant, w, h, t, seconds);
                break;
            case "waves":
                drawWaves(c, variant, w, h, t, seconds);
                break;
            case "checker":
                drawChecker(c, variant, w, h, e);
                break;
            case "shutters":
                drawShutters(c, variant, w, h, e);
                break;
            case "ripples":
                drawRipples(c, variant, w, h, e);
                break;
            case "folds":
                drawFolds(c, variant, w, h, e);
                break;
            case "bars":
                drawBars(c, variant, w, h, e, seconds);
                break;
            case "dots":
                drawDots(c, variant, w, h, t, seconds);
                break;
            case "slices":
                drawSlices(c, variant, w, h, e, seconds);
                break;
            case "weave":
                drawWeave(c, variant, w, h, t, seconds);
                break;
            case "flash":
                drawFlash(c, variant, w, h, e);
                break;
            case "bubbles":
                drawBubbles(c, variant, w, h, e, seconds);
                break;
        }
    }

    function drawSticker(c, v, w, h, e, seconds) {
        for (let i = 0; i < v.grid.rows; i++) {
            const r = (58 + i * (24 + v.grid.cell * 0.42)) * e;
            c.save();
            c.translate(w / 2, h / 2);
            c.rotate(v.angleRad + seconds * v.wave + i * .45);
            c.strokeStyle = v.colors[i % v.colors.length];
            c.lineWidth = 8;
            c.setLineDash([22, 14]);
            c.strokeRect(-r, -r, r * 2, r * 2);
            c.restore();
        }
        c.setLineDash([]);
    }

    function drawCards(c, v, w, h, e) {
        for (let i = 0; i < v.grid.cols; i++) {
            const p = (i / Math.max(v.grid.cols - 1, 1)) * 2 - 1;
            const x = w / 2 + p * w * .36 * e;
            const y = h / 2 + Math.sin(i + v.phase) * 44 * v.spread;
            drawCardShape(c, x, y, 180 * v.size, 120 * v.size, i * 7 + v.angle, v.colors[i % v.colors.length], e);
        }
    }

    function drawBurst(c, v, w, h, e, seconds) {
        const cx = w / 2;
        const cy = h / 2;
        const count = Math.round(64 * v.density);
        for (let i = 0; i < count; i++) {
            const a = (i / count) * Math.PI * 2 + v.angleRad + seconds * .08;
            const r1 = 60 * e;
            const r2 = (Math.max(w, h) * .58) * e * (0.72 + (i % 5) * .08);
            c.strokeStyle = v.colors[i % v.colors.length];
            c.lineWidth = i % 4 === 0 ? 8 : 3;
            c.beginPath();
            c.moveTo(cx + Math.cos(a) * r1, cy + Math.sin(a) * r1);
            c.lineTo(cx + Math.cos(a) * r2, cy + Math.sin(a) * r2);
            c.stroke();
        }
    }

    function drawConfetti(c, v, w, h, t, seconds) {
        const count = Math.round(90 * v.density);
        for (let i = 0; i < count; i++) {
            const p = (t + i * .021) % 1;
            const x = w * ((i * 37 + Math.round(v.seed * 100)) % 100) / 100 + Math.sin(seconds * 3 + i + v.phase) * 40 * v.spread;
            const y = h * (1.12 - p * 1.35);
            c.save();
            c.translate(x, y);
            c.rotate(seconds * 2 + i);
            c.fillStyle = v.colors[i % v.colors.length];
            c.strokeStyle = INK;
            c.lineWidth = 2;
            c.fillRect(-12, -8, 24, 16);
            c.strokeRect(-12, -8, 24, 16);
            c.restore();
        }
    }

    function drawWaves(c, v, w, h, t, seconds) {
        c.lineCap = "round";
        for (let band = 0; band < v.grid.rows; band++) {
            c.beginPath();
            const y0 = h * (.16 + band * (.72 / Math.max(v.grid.rows - 1, 1)));
            for (let x = -40; x <= w + 40; x += 28) {
                const y = y0 + Math.sin(x * .012 * v.wave + seconds * 2 + band + v.phase) * 34 * Math.sin(t * Math.PI) * v.spread;
                if (x === -40) c.moveTo(x, y);
                else c.lineTo(x, y);
            }
            c.strokeStyle = v.colors[band % v.colors.length];
            c.lineWidth = 10 + band;
            c.stroke();
        }
        c.lineCap = "butt";
    }

    function drawChecker(c, v, w, h, e) {
        const cols = v.grid.cols;
        const rows = v.grid.rows;
        const cellW = w / cols;
        const cellH = h / rows;
        for (let y = 0; y < rows; y++) {
            for (let x = 0; x < cols; x++) {
                const delay = (x + y) / (cols + rows);
                const scale = Math.max(0, Math.min(1, (e - delay * .38) / .42));
                if (!scale) continue;
                c.fillStyle = v.colors[(x + y) % v.colors.length];
                c.strokeStyle = INK;
                c.lineWidth = 3;
                c.save();
                c.translate(x * cellW + cellW / 2, y * cellH + cellH / 2);
                c.rotate(((x + y) % 2 ? -1 : 1) * .08 + v.angleRad * .08);
                c.scale(scale, scale);
                c.fillRect(-cellW / 2, -cellH / 2, cellW, cellH);
                c.strokeRect(-cellW / 2, -cellH / 2, cellW, cellH);
                c.restore();
            }
        }
    }

    function drawShutters(c, v, w, h, e) {
        for (let i = 0; i < v.grid.rows + 2; i++) {
            const y = i * h / (v.grid.rows + 2);
            const gap = Math.sin(e * Math.PI) * w * .55;
            c.fillStyle = v.colors[i % v.colors.length];
            c.strokeStyle = INK;
            c.lineWidth = 4;
            const rowH = h / (v.grid.rows + 2) + 5;
            c.fillRect(-gap, y, w * .5, rowH);
            c.strokeRect(-gap, y, w * .5, rowH);
            c.fillRect(w * .5 + gap, y, w * .5 + gap, rowH);
            c.strokeRect(w * .5 + gap, y, w * .5 + gap, rowH);
        }
    }

    function drawRipples(c, v, w, h, e) {
        for (let i = 0; i < v.grid.rows + 3; i++) {
            const p = (e + i * (0.08 + v.seed * 0.05)) % 1;
            const r = p * Math.max(w, h) * .52;
            c.strokeStyle = v.colors[i % v.colors.length];
            c.lineWidth = 12 * (1 - p) + 2;
            c.beginPath();
            c.arc(w / 2, h / 2, r, 0, Math.PI * 2);
            c.stroke();
        }
    }

    function drawFolds(c, v, w, h, e) {
        const cols = Math.max(3, Math.min(v.grid.cols, 6));
        const rows = Math.max(2, Math.min(v.grid.rows, 4));
        for (let i = 0; i < cols * rows; i++) {
            const x = (i % cols) * w / Math.max(cols - 1, 1);
            const y = Math.floor(i / cols) * h / Math.max(rows - 1, 1);
            c.fillStyle = v.colors[i % v.colors.length];
            c.strokeStyle = INK;
            c.lineWidth = 4;
            c.beginPath();
            c.moveTo(x, y);
            c.lineTo(x + w / cols * e, y + (i % 2 ? h / rows : 0));
            c.lineTo(x + (i % 2 ? 0 : w / cols), y + h / rows * e);
            c.closePath();
            c.fill();
            c.stroke();
        }
    }

    function drawBars(c, v, w, h, e, seconds) {
        const count = Math.round(24 * v.density);
        for (let i = 0; i < count; i++) {
            const y = i * h / count;
            const x = Math.sin(seconds * 4 * v.wave + i + v.phase) * 80 * v.spread;
            c.fillStyle = v.colors[i % v.colors.length];
            c.fillRect(x - w * (1 - e), y, w * (.6 + e * .55), 8 + (i % 4) * 5);
        }
    }

    function drawDots(c, v, w, h, t, seconds) {
        const step = Math.max(14, v.grid.cell * 0.8);
        for (let y = -step; y < h + step; y += step) {
            for (let x = -step; x < w + step; x += step) {
                const dx = x - w / 2;
                const dy = y - h / 2;
                const wave = Math.sin(Math.sqrt(dx * dx + dy * dy) * .035 * v.wave - seconds * 5 + v.phase);
                const r = Math.max(1, (4 + wave * 7) * Math.sin(t * Math.PI));
                c.fillStyle = v.colors[Math.abs(Math.floor((x + y) / step)) % v.colors.length];
                c.beginPath();
                c.arc(x, y, r, 0, Math.PI * 2);
                c.fill();
            }
        }
    }

    function drawSlices(c, v, w, h, e, seconds) {
        const count = Math.round(18 * v.density);
        for (let i = 0; i < count; i++) {
            const a = (i / count) * Math.PI * 2 + v.angleRad + seconds * .6;
            const r = Math.max(w, h) * .28 * e;
            const x = w / 2 + Math.cos(a) * r;
            const y = h / 2 + Math.sin(a) * r;
            c.save();
            c.translate(x, y);
            c.rotate(a);
            c.fillStyle = v.colors[i % v.colors.length];
            c.strokeStyle = INK;
            c.lineWidth = 3;
            c.beginPath();
            c.moveTo(-18, -70);
            c.lineTo(74, -28);
            c.lineTo(34, 70);
            c.lineTo(-70, 22);
            c.closePath();
            c.fill();
            c.stroke();
            c.restore();
        }
    }

    function drawWeave(c, v, w, h, t, seconds) {
        c.lineCap = "square";
        for (let i = 0; i < v.grid.rows + 2; i++) {
            const y = h * (.08 + i * (.84 / (v.grid.rows + 1)));
            c.strokeStyle = v.colors[i % v.colors.length];
            c.lineWidth = 18;
            c.beginPath();
            for (let x = -80; x <= w + 80; x += 40) {
                const yy = y + Math.sin(x * .015 * v.wave + seconds * 3 + i + v.phase) * 22 * Math.sin(t * Math.PI) * v.spread;
                if (x === -80) c.moveTo(x, yy);
                else c.lineTo(x, yy);
            }
            c.stroke();
        }
        for (let i = 0; i < Math.max(5, Math.round(v.grid.cols * .55)); i++) {
            const x = w * (.08 + i * (.84 / Math.max(4, Math.round(v.grid.cols * .55))));
            c.strokeStyle = v.colors[(i + 2) % v.colors.length];
            c.lineWidth = 14;
            c.beginPath();
            c.moveTo(x + Math.sin(seconds + i) * 18, -40);
            c.lineTo(x - Math.sin(seconds + i) * 18, h + 40);
            c.stroke();
        }
        c.lineCap = "butt";
    }

    function drawFlash(c, v, w, h, e) {
        const pulse = Math.sin(e * Math.PI);
        c.fillStyle = alpha(PAPER, .78 * pulse);
        c.fillRect(0, 0, w, h);
        for (let i = 0; i < v.grid.cols; i++) {
            drawCardShape(
                c,
                w * ((i * 17 + Math.round(v.seed * 80)) % 100) / 100,
                h * ((i * 29 + Math.round(v.seed * 60)) % 100) / 100,
                (220 + i * 10) * v.size,
                (84 + (i % 4) * 28) * v.size,
                i * 11 + v.angle,
                v.colors[i % v.colors.length],
                pulse,
            );
        }
    }

    function drawBubbles(c, v, w, h, e, seconds) {
        const count = Math.round(34 * v.density);
        for (let i = 0; i < count; i++) {
            const a = (i / count) * Math.PI * 2 + v.angleRad + seconds * .35;
            const r = (60 + (i % 8) * 42) * e;
            const x = w / 2 + Math.cos(a) * r;
            const y = h / 2 + Math.sin(a) * r;
            const d = (28 + (i % 6) * 18) * v.size;
            c.fillStyle = alpha(v.colors[i % v.colors.length], .62);
            c.strokeStyle = INK;
            c.lineWidth = 3;
            c.beginPath();
            c.arc(x, y, d, 0, Math.PI * 2);
            c.fill();
            c.stroke();
        }
    }

    function drawCardShape(c, x, y, w, h, rot, fill, scale) {
        c.save();
        c.translate(x, y);
        c.rotate((rot * Math.PI) / 180);
        c.scale(scale, scale);
        c.fillStyle = fill;
        c.strokeStyle = INK;
        c.lineWidth = 5;
        c.fillRect(-w / 2, -h / 2, w, h);
        c.strokeRect(-w / 2, -h / 2, w, h);
        c.restore();
    }

    function createFlecks(variant, count) {
        return Array.from({ length: count }, () => ({
            x: Math.random(),
            y: Math.random(),
            size: rand(1.5, 5),
            speed: rand(.18, 1.2) * variant.wave,
            phase: rand(0, Math.PI * 2),
            drift: rand(6, 34) * variant.spread,
            color: variant.colors[Math.floor(Math.random() * variant.colors.length)],
        }));
    }

    function drawFlecks(c, flecks, w, h, t, seconds) {
        const visible = Math.sin(t * Math.PI);
        for (const fleck of flecks) {
            const x = (fleck.x * w + Math.cos(seconds * fleck.speed + fleck.phase) * fleck.drift + w) % w;
            const y = (fleck.y * h + Math.sin(seconds * fleck.speed + fleck.phase) * fleck.drift + h) % h;
            c.fillStyle = alpha(fleck.color, .34 * visible);
            c.fillRect(x, y, fleck.size, fleck.size);
        }
    }

    function rand(min, max) {
        return min + Math.random() * (max - min);
    }

    function speedMs(ms) {
        return Math.max(0, Math.round(ms / ENTRY_SPEED));
    }

    function speedSec(ms) {
        return speedMs(ms) / 1000;
    }

    function generateVariant(base) {
        const seed = Math.random();
        const shift = Math.floor(rand(0, base.colors.length));
        const palette = rotate(base.colors, shift);
        if (Math.random() > 0.55) {
            const swapIndex = Math.floor(rand(1, palette.length));
            [palette[0], palette[swapIndex]] = [palette[swapIndex], palette[0]];
        }
        const algorithm = ["radial", "diagonal", "grid", "spiral", "fold", "scatter"][Math.floor(rand(0, 6))];
        const profile = {
            radial: { density: [0.88, 1.3], cell: [20, 34], spread: [0.9, 1.24] },
            diagonal: { density: [0.72, 1.08], cell: [24, 44], spread: [1.06, 1.42] },
            grid: { density: [1.0, 1.45], cell: [16, 30], spread: [0.82, 1.12] },
            spiral: { density: [0.86, 1.32], cell: [18, 36], spread: [1.0, 1.34] },
            fold: { density: [0.78, 1.12], cell: [28, 48], spread: [0.88, 1.18] },
            scatter: { density: [1.08, 1.52], cell: [18, 34], spread: [1.04, 1.44] },
        }[algorithm];
        const grid = {
            cols: Math.floor(rand(7, 16)),
            rows: Math.floor(rand(5, 11)),
            cell: rand(profile.cell[0], profile.cell[1]),
        };
        const angle = rand(-34, 34);
        return {
            ...base,
            colors: palette,
            palette,
            algorithm: algorithm,
            grid: grid,
            density: rand(profile.density[0], profile.density[1]),
            angle: angle,
            angleRad: (angle * Math.PI) / 180,
            seed: seed,
            phase: seed * Math.PI * 2,
            wave: rand(0.76, 1.42),
            dot: rand(1.0, 3.2),
            size: rand(0.78, 1.26),
            spread: rand(profile.spread[0], profile.spread[1]),
            rotation: rand(0.72, 1.45),
            pace: rand(0.82, 1.12),
        };
    }

    function rotate(items, count) {
        return items.slice(count).concat(items.slice(0, count));
    }

    function easeOutCubic(t) {
        return 1 - Math.pow(1 - t, 3);
    }

    function tint(hex, amount) {
        const rgb = toRgb(hex);
        return `rgb(${Math.round(rgb.r + (255 - rgb.r) * amount)}, ${Math.round(rgb.g + (255 - rgb.g) * amount)}, ${Math.round(rgb.b + (255 - rgb.b) * amount)})`;
    }

    function alpha(hex, value) {
        const rgb = toRgb(hex);
        return `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${value})`;
    }

    function toRgb(hex) {
        const raw = hex.replace("#", "");
        const value = parseInt(raw, 16);
        return {
            r: (value >> 16) & 255,
            g: (value >> 8) & 255,
            b: value & 255,
        };
    }
})();
