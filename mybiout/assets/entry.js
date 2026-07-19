(function () {
    // 版本号仅主页常驻; 子页面不挂
    function 是否主页() {
        var 路径 = (location.pathname || "/").replace(/\\/g, "/");
        return 路径 === "/" || 路径 === "" || /\/index\.html?$/i.test(路径);
    }
    function 挂载版本号() {
        if (!document.body || !是否主页()) {
            var 旧 = document.querySelector(".mybiout-version");
            if (旧) 旧.remove();
            return;
        }
        let 节点 = document.querySelector(".mybiout-version");
        if (!节点) {
            节点 = document.createElement("div");
            节点.className = "mybiout-version";
            节点.setAttribute("aria-hidden", "true");
            document.body.appendChild(节点);
        }
        fetch("/api/version")
            .then(function (响应) {
                return 响应.json();
            })
            .then(function (数据) {
                if (数据 && 数据.version) {
                    节点.textContent = "v" + 数据.version;
                }
            })
            .catch(function () {});
    }
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", 挂载版本号);
    } else {
        挂载版本号();
    }

    const 粉 = "#E85B8A";
    const 橙 = "#F5A623";
    const 蓝 = "#00AEEC";
    const 墨 = "#2B1822";
    const 纸 = "#FFFFFF";
    const 入口速度 = 1.55;
    const 基础时序 = {
        ready: 520,
        fallbackReady: 640,
        画布: 1280,
        渲染: 1560,
        remove: 1680,
        overlayDelay: 1180,
        overlayDuration: 380,
    };

    const 入口变体表 = [
        { name: "sticker-pop", mode: "sticker", family: "manga", colors: [粉, 橙, 蓝, 纸] },
        { name: "card-slam", mode: "cards", family: "wipe", colors: [蓝, 纸, 粉, 橙] },
        { name: "manga-burst", mode: "burst", family: "manga", colors: [橙, 粉, 纸, 蓝] },
        { name: "confetti-cannon", mode: "confetti", family: "manga", colors: [粉, 橙, 蓝, 纸] },
        { name: "wave-ribbons", mode: "waves", family: "soft", colors: [蓝, 粉, 橙, 纸] },
        { name: "checker-wipe", mode: "checker", family: "wipe", colors: [粉, 纸, 蓝, 橙] },
        { name: "shutter-cards", mode: "shutters", family: "wipe", colors: [橙, 粉, 纸, 蓝] },
        { name: "stamp-ripple", mode: "ripples", family: "manga", colors: [粉, 纸, 橙, 蓝] },
        { name: "paper-fold", mode: "folds", family: "wipe", colors: [纸, 蓝, 粉, 橙] },
        { name: "scan-bars", mode: "bars", family: "wipe", colors: [蓝, 纸, 粉, 橙] },
        { name: "dot-matrix", mode: "dots", family: "soft", colors: [粉, 橙, 蓝, 纸] },
        { name: "carousel-slices", mode: "slices", family: "manga", colors: [蓝, 橙, 粉, 纸] },
        { name: "ribbon-weave", mode: "weave", family: "soft", colors: [橙, 蓝, 粉, 纸] },
        { name: "flash-cards", mode: "flash", family: "wipe", colors: [纸, 粉, 蓝, 橙] },
        { name: "bubble-splash", mode: "bubbles", family: "soft", colors: [蓝, 粉, 橙, 纸] },
    ];

    window.MYBIOUT_入口变体表 = 入口变体表.map((变体) => 变体.name);

    const 遮罩 = document.querySelector(".mybiout-entry-overlay");
    if (!遮罩) {
        document.body.classList.add("mybiout-entry-ready");
        return;
    }

    const 减少动态 = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (减少动态) {
        遮罩.remove();
        document.body.classList.add("mybiout-entry-ready");
        return;
    }

    const 变体 = 入口变体表[Math.floor(Math.random() * 入口变体表.length)];
    const 生成后 = 生成变体(变体);
    遮罩.classList.add(`entry-${变体.name}`);
    遮罩.dataset.entryFamily = 变体.family;
    遮罩.style.setProperty("--entry-overlay-delay", `${按毫秒加速(基础时序.overlayDelay)}ms`);
    遮罩.style.setProperty("--entry-overlay-duration", `${按毫秒加速(基础时序.overlayDuration)}ms`);
    遮罩.style.setProperty("--entry-core-duration", `${按秒加速(1250)}s`);

    let 画布 = 遮罩.querySelector(".mybiout-entry-canvas");
    if (!画布) {
        画布 = document.createElement("canvas");
        画布.className = "mybiout-entry-canvas";
        遮罩.prepend(画布);
    }

    let 舞台 = 遮罩.querySelector(".mybiout-entry-stage");
    if (!舞台) {
        舞台 = document.createElement("div");
        舞台.className = "mybiout-entry-stage";
        遮罩.appendChild(舞台);
    }

    let 核心 = 遮罩.querySelector(".mybiout-entry-core");
    if (!核心) {
        核心 = document.createElement("div");
        核心.className = "mybiout-entry-core";
        舞台.appendChild(核心);
    }

    核心.style.setProperty("--entry-core-bg", 生成后.调色板[0]);
    核心.style.setProperty("--entry-shadow", 生成后.调色板[2]);
    核心.style.setProperty("--entry-tilt", `${生成后.angle * 0.08}deg`);

    const 画笔 = 画布.getContext("2d", { alpha: true });
    // 斑点数量上限：降低首屏主线程压力（点 Man 等跳转时体感更顺）
    const 斑点群 = 生成斑点(生成后, Math.min(72, Math.round(90 * 生成后.density)));
    let width = 0;
    let height = 0;
    let dpr = 1;
    let 起始时间 = performance.now();
    let 已发就绪 = false;

    function 调整尺寸() {
        dpr = Math.min(window.devicePixelRatio || 1, 2);
        width = Math.max(1, window.innerWidth);
        height = Math.max(1, window.innerHeight);
        画布.width = Math.floor(width * dpr);
        画布.height = Math.floor(height * dpr);
        画布.style.width = `${width}px`;
        画布.style.height = `${height}px`;
        画笔.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    调整尺寸();
    构建碎片(遮罩, 变体, 生成后);
    window.addEventListener("resize", 调整尺寸, { passive: true });
    requestAnimationFrame(渲染);

    window.setTimeout(() => {
        document.body.classList.add("mybiout-entry-ready");
    }, 按毫秒加速(基础时序.fallbackReady));

    window.setTimeout(() => {
        window.removeEventListener("resize", 调整尺寸);
        遮罩.remove();
    }, 按毫秒加速(基础时序.remove));

    function 渲染(now) {
        const 已过 = now - 起始时间;
        const t = Math.min(已过 / 按毫秒加速(基础时序.画布), 1);
        const e = 缓出三次(t);

        画笔.clearRect(0, 0, width, height);
        绘制纸面(画笔, 生成后, width, height, t);
        绘制模式(画笔, 生成后, width, height, t, e, 已过 * 0.001 * 入口速度);
        绘制斑点(画笔, 斑点群, width, height, t, 已过 * 0.001);

        if (!已发就绪 && 已过 > 按毫秒加速(基础时序.ready)) {
            已发就绪 = true;
            document.body.classList.add("mybiout-entry-ready");
        }

        if (已过 < 按毫秒加速(基础时序.渲染) && 遮罩.isConnected) {
            requestAnimationFrame(渲染);
        }
    }

    function 构建碎片(root, 变体, 生成后) {
        const 基础 = {
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
        }[变体.mode] || [32, "slice"];
        const 数量 = Math.max(6, Math.min(36, Math.round(基础[0] * 生成后.density * 0.62)));

        for (let i = 0; i < 数量; i++) {
            const type = 选择碎片类型(基础[1], i, 变体.mode);
            const 碎片 = document.createElement("i");
            碎片.className = `mybiout-entry-piece ${type}`;
            const size = 碎片尺寸(type, i, 变体.mode, 生成后);
            const color = 生成后.调色板[i % 生成后.调色板.length];
            碎片.style.left = `${随机数(-8, 100)}vw`;
            碎片.style.top = `${随机数(-8, 100)}vh`;
            碎片.style.width = `${size.w}px`;
            碎片.style.height = `${size.h}px`;
            碎片.style.setProperty("--piece-fill", color);
            碎片.style.setProperty("--piece-ink", type === "triangle" ? "transparent" : 墨);
            碎片.style.setProperty("--piece-shadow", 透明色(墨, 0.18));
            root.appendChild(碎片);
            动画碎片(碎片, i, 变体.mode, 生成后);
        }
    }

    function 选择碎片类型(type, index, mode) {
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

    function 碎片尺寸(type, index, mode, 生成后) {
        const sizeJitter = 生成后.size;
        if (type === "line") {
            return { w: 随机数(90, mode === "burst" ? 390 : 260) * sizeJitter, h: 随机数(5, 14) * sizeJitter };
        }
        if (type === "dot") {
            const d = 随机数(mode === "dots" ? 5 : 12, mode === "bubbles" ? 84 : 42) * sizeJitter;
            return { w: d, h: d };
        }
        if (type === "triangle") {
            const d = 随机数(38, 120) * sizeJitter;
            return { w: d, h: d * 随机数(0.72, 1.22) };
        }
        if (type === "slice") {
            return { w: 随机数(34, 120) * sizeJitter, h: 随机数(26, 92) * sizeJitter };
        }
        const side = (mode === "checker" ? 随机数(34, 70) : 随机数(64, 170)) * sizeJitter;
        return { w: side * 随机数(0.8, 1.55), h: side };
    }

    function 动画碎片(碎片, index, mode, 生成后) {
        const a = 生成后.angleRad + 随机数(0, Math.PI * 2);
        const span = Math.max(window.innerWidth, window.innerHeight);
        const spread = 生成后.spread;
        const startX = mode === "shutters" ? (index % 2 ? -span : span) : Math.cos(a) * 随机数(120, span * 0.45) * spread;
        const startY = mode === "bars" ? 随机数(-span * 0.3, span * 0.3) * spread : Math.sin(a) * 随机数(80, span * 0.36) * spread;
        const endX = mode === "checker" ? 0 : Math.cos(a + Math.PI) * 随机数(30, span * 0.18) * spread;
        const endY = mode === "checker" ? 0 : Math.sin(a + Math.PI) * 随机数(30, span * 0.14) * spread;
        const rotA = 生成后.角度 * 0.3 + 随机数(-34, 34);
        const rotB = rotA + 随机数(60, 260) * (index % 2 ? -1 : 1) * 生成后.rotation;
        const delay = 按毫秒加速(随机数(0, mode === "flash" ? 180 : 420));
        const duration = 按毫秒加速(随机数(920, mode === "bubbles" ? 1720 : 1380) * 生成后.pace);

        碎片.animate(
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

    function 绘制纸面(c, 变体, w, h, t) {
        const wash = c.createLinearGradient(0, 0, w, h);
        wash.addColorStop(0, "#FFFFFF");
        wash.addColorStop(0.5, 染色(变体.colors[0], 0.9));
        wash.addColorStop(1, 染色(变体.colors[2], 0.9));
        c.fillStyle = wash;
        c.fillRect(0, 0, w, h);

        c.globalAlpha = 0.18;
        c.fillStyle = 变体.colors[0];
        const step = 变体.网格.cell;
        if (变体.算法 === "diagonal") {
            c.save();
            c.rotate(变体.angleRad * 0.25);
            for (let y = -h; y < h * 1.6; y += step * 1.4) {
                c.fillRect(-w * 0.2, y, w * 1.4, 4 + 变体.dot);
            }
            c.restore();
        } else if (变体.算法 === "fold") {
            for (let x = -step; x < w + step; x += step * 2.2) {
                c.fillRect(x, 0, step * 0.22, h);
            }
            for (let y = -step; y < h + step; y += step * 2.2) {
                c.fillRect(0, y, w, step * 0.18);
            }
        } else {
            for (let y = -step; y < h + step; y += step) {
                for (let x = -step; x < w + step; x += step) {
                    const radialGate = 变体.算法 === "radial"
                        ? Math.sin(Math.hypot(x - w / 2, y - h / 2) * 0.025 + 变体.phase) > -0.28
                        : true;
                    if (radialGate && (Math.floor(x / step) + Math.floor(y / step)) % 2 === 0) {
                        c.beginPath();
                        c.arc(x + step * 0.3, y + step * 0.3, 1.4 + Math.sin(t * Math.PI) * 变体.dot, 0, Math.PI * 2);
                        c.fill();
                    }
                }
            }
        }
        c.globalAlpha = 1;
    }

    function 绘制模式(c, 变体, w, h, t, e, 秒数) {
        switch (变体.mode) {
            case "sticker":
                绘制贴纸(c, 变体, w, h, e, 秒数);
                break;
            case "cards":
                绘制卡片(c, 变体, w, h, e);
                break;
            case "burst":
                绘制爆发(c, 变体, w, h, e, 秒数);
                break;
            case "confetti":
                绘制彩纸(c, 变体, w, h, t, 秒数);
                break;
            case "waves":
                绘制波带(c, 变体, w, h, t, 秒数);
                break;
            case "checker":
                绘制棋盘(c, 变体, w, h, e);
                break;
            case "shutters":
                绘制快门(c, 变体, w, h, e);
                break;
            case "ripples":
                绘制涟漪(c, 变体, w, h, e);
                break;
            case "folds":
                绘制折页(c, 变体, w, h, e);
                break;
            case "bars":
                绘制条带(c, 变体, w, h, e, 秒数);
                break;
            case "dots":
                绘制圆点(c, 变体, w, h, t, 秒数);
                break;
            case "slices":
                绘制切片(c, 变体, w, h, e, 秒数);
                break;
            case "weave":
                绘制编织(c, 变体, w, h, t, 秒数);
                break;
            case "flash":
                绘制闪片(c, 变体, w, h, e);
                break;
            case "bubbles":
                绘制气泡(c, 变体, w, h, e, 秒数);
                break;
        }
    }

    function 绘制贴纸(c, v, w, h, e, 秒数) {
        for (let i = 0; i < v.网格.rows; i++) {
            const r = (58 + i * (24 + v.网格.cell * 0.42)) * e;
            c.save();
            c.translate(w / 2, h / 2);
            c.rotate(v.angleRad + 秒数 * v.wave + i * .45);
            c.strokeStyle = v.colors[i % v.colors.length];
            c.lineWidth = 8;
            c.setLineDash([22, 14]);
            c.strokeRect(-r, -r, r * 2, r * 2);
            c.restore();
        }
        c.setLineDash([]);
    }

    function 绘制卡片(c, v, w, h, e) {
        for (let i = 0; i < v.网格.cols; i++) {
            const p = (i / Math.max(v.网格.cols - 1, 1)) * 2 - 1;
            const x = w / 2 + p * w * .36 * e;
            const y = h / 2 + Math.sin(i + v.phase) * 44 * v.spread;
            绘制卡片形(c, x, y, 180 * v.size, 120 * v.size, i * 7 + v.角度, v.colors[i % v.colors.length], e);
        }
    }

    function 绘制爆发(c, v, w, h, e, 秒数) {
        const cx = w / 2;
        const cy = h / 2;
        const 数量 = Math.round(64 * v.density);
        for (let i = 0; i < 数量; i++) {
            const a = (i / 数量) * Math.PI * 2 + v.angleRad + 秒数 * .08;
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

    function 绘制彩纸(c, v, w, h, t, 秒数) {
        const 数量 = Math.round(90 * v.density);
        for (let i = 0; i < 数量; i++) {
            const p = (t + i * .021) % 1;
            const x = w * ((i * 37 + Math.round(v.种子 * 100)) % 100) / 100 + Math.sin(秒数 * 3 + i + v.phase) * 40 * v.spread;
            const y = h * (1.12 - p * 1.35);
            c.save();
            c.translate(x, y);
            c.rotate(秒数 * 2 + i);
            c.fillStyle = v.colors[i % v.colors.length];
            c.strokeStyle = 墨;
            c.lineWidth = 2;
            c.fillRect(-12, -8, 24, 16);
            c.strokeRect(-12, -8, 24, 16);
            c.restore();
        }
    }

    function 绘制波带(c, v, w, h, t, 秒数) {
        c.lineCap = "round";
        for (let band = 0; band < v.网格.rows; band++) {
            c.beginPath();
            const y0 = h * (.16 + band * (.72 / Math.max(v.网格.rows - 1, 1)));
            for (let x = -40; x <= w + 40; x += 28) {
                const y = y0 + Math.sin(x * .012 * v.wave + 秒数 * 2 + band + v.phase) * 34 * Math.sin(t * Math.PI) * v.spread;
                if (x === -40) c.moveTo(x, y);
                else c.lineTo(x, y);
            }
            c.strokeStyle = v.colors[band % v.colors.length];
            c.lineWidth = 10 + band;
            c.stroke();
        }
        c.lineCap = "butt";
    }

    function 绘制棋盘(c, v, w, h, e) {
        const cols = v.网格.cols;
        const rows = v.网格.rows;
        const cellW = w / cols;
        const cellH = h / rows;
        for (let y = 0; y < rows; y++) {
            for (let x = 0; x < cols; x++) {
                const delay = (x + y) / (cols + rows);
                const scale = Math.max(0, Math.min(1, (e - delay * .38) / .42));
                if (!scale) continue;
                c.fillStyle = v.colors[(x + y) % v.colors.length];
                c.strokeStyle = 墨;
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

    function 绘制快门(c, v, w, h, e) {
        for (let i = 0; i < v.网格.rows + 2; i++) {
            const y = i * h / (v.网格.rows + 2);
            const gap = Math.sin(e * Math.PI) * w * .55;
            c.fillStyle = v.colors[i % v.colors.length];
            c.strokeStyle = 墨;
            c.lineWidth = 4;
            const rowH = h / (v.网格.rows + 2) + 5;
            c.fillRect(-gap, y, w * .5, rowH);
            c.strokeRect(-gap, y, w * .5, rowH);
            c.fillRect(w * .5 + gap, y, w * .5 + gap, rowH);
            c.strokeRect(w * .5 + gap, y, w * .5 + gap, rowH);
        }
    }

    function 绘制涟漪(c, v, w, h, e) {
        for (let i = 0; i < v.网格.rows + 3; i++) {
            const p = (e + i * (0.08 + v.种子 * 0.05)) % 1;
            const r = p * Math.max(w, h) * .52;
            c.strokeStyle = v.colors[i % v.colors.length];
            c.lineWidth = 12 * (1 - p) + 2;
            c.beginPath();
            c.arc(w / 2, h / 2, r, 0, Math.PI * 2);
            c.stroke();
        }
    }

    function 绘制折页(c, v, w, h, e) {
        const cols = Math.max(3, Math.min(v.网格.cols, 6));
        const rows = Math.max(2, Math.min(v.网格.rows, 4));
        for (let i = 0; i < cols * rows; i++) {
            const x = (i % cols) * w / Math.max(cols - 1, 1);
            const y = Math.floor(i / cols) * h / Math.max(rows - 1, 1);
            c.fillStyle = v.colors[i % v.colors.length];
            c.strokeStyle = 墨;
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

    function 绘制条带(c, v, w, h, e, 秒数) {
        const 数量 = Math.round(24 * v.density);
        for (let i = 0; i < 数量; i++) {
            const y = i * h / 数量;
            const x = Math.sin(秒数 * 4 * v.wave + i + v.phase) * 80 * v.spread;
            c.fillStyle = v.colors[i % v.colors.length];
            c.fillRect(x - w * (1 - e), y, w * (.6 + e * .55), 8 + (i % 4) * 5);
        }
    }

    function 绘制圆点(c, v, w, h, t, 秒数) {
        const step = Math.max(14, v.网格.cell * 0.8);
        for (let y = -step; y < h + step; y += step) {
            for (let x = -step; x < w + step; x += step) {
                const dx = x - w / 2;
                const dy = y - h / 2;
                const wave = Math.sin(Math.sqrt(dx * dx + dy * dy) * .035 * v.wave - 秒数 * 5 + v.phase);
                const r = Math.max(1, (4 + wave * 7) * Math.sin(t * Math.PI));
                c.fillStyle = v.colors[Math.abs(Math.floor((x + y) / step)) % v.colors.length];
                c.beginPath();
                c.arc(x, y, r, 0, Math.PI * 2);
                c.fill();
            }
        }
    }

    function 绘制切片(c, v, w, h, e, 秒数) {
        const 数量 = Math.round(18 * v.density);
        for (let i = 0; i < 数量; i++) {
            const a = (i / 数量) * Math.PI * 2 + v.angleRad + 秒数 * .6;
            const r = Math.max(w, h) * .28 * e;
            const x = w / 2 + Math.cos(a) * r;
            const y = h / 2 + Math.sin(a) * r;
            c.save();
            c.translate(x, y);
            c.rotate(a);
            c.fillStyle = v.colors[i % v.colors.length];
            c.strokeStyle = 墨;
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

    function 绘制编织(c, v, w, h, t, 秒数) {
        c.lineCap = "square";
        for (let i = 0; i < v.网格.rows + 2; i++) {
            const y = h * (.08 + i * (.84 / (v.网格.rows + 1)));
            c.strokeStyle = v.colors[i % v.colors.length];
            c.lineWidth = 18;
            c.beginPath();
            for (let x = -80; x <= w + 80; x += 40) {
                const yy = y + Math.sin(x * .015 * v.wave + 秒数 * 3 + i + v.phase) * 22 * Math.sin(t * Math.PI) * v.spread;
                if (x === -80) c.moveTo(x, yy);
                else c.lineTo(x, yy);
            }
            c.stroke();
        }
        for (let i = 0; i < Math.max(5, Math.round(v.网格.cols * .55)); i++) {
            const x = w * (.08 + i * (.84 / Math.max(4, Math.round(v.网格.cols * .55))));
            c.strokeStyle = v.colors[(i + 2) % v.colors.length];
            c.lineWidth = 14;
            c.beginPath();
            c.moveTo(x + Math.sin(秒数 + i) * 18, -40);
            c.lineTo(x - Math.sin(秒数 + i) * 18, h + 40);
            c.stroke();
        }
        c.lineCap = "butt";
    }

    function 绘制闪片(c, v, w, h, e) {
        const pulse = Math.sin(e * Math.PI);
        c.fillStyle = 透明色(纸, .78 * pulse);
        c.fillRect(0, 0, w, h);
        for (let i = 0; i < v.网格.cols; i++) {
            绘制卡片形(
                c,
                w * ((i * 17 + Math.round(v.种子 * 80)) % 100) / 100,
                h * ((i * 29 + Math.round(v.种子 * 60)) % 100) / 100,
                (220 + i * 10) * v.size,
                (84 + (i % 4) * 28) * v.size,
                i * 11 + v.角度,
                v.colors[i % v.colors.length],
                pulse,
            );
        }
    }

    function 绘制气泡(c, v, w, h, e, 秒数) {
        const 数量 = Math.round(34 * v.density);
        for (let i = 0; i < 数量; i++) {
            const a = (i / 数量) * Math.PI * 2 + v.angleRad + 秒数 * .35;
            const r = (60 + (i % 8) * 42) * e;
            const x = w / 2 + Math.cos(a) * r;
            const y = h / 2 + Math.sin(a) * r;
            const d = (28 + (i % 6) * 18) * v.size;
            c.fillStyle = 透明色(v.colors[i % v.colors.length], .62);
            c.strokeStyle = 墨;
            c.lineWidth = 3;
            c.beginPath();
            c.arc(x, y, d, 0, Math.PI * 2);
            c.fill();
            c.stroke();
        }
    }

    function 绘制卡片形(c, x, y, w, h, rot, fill, scale) {
        c.save();
        c.translate(x, y);
        c.rotate((rot * Math.PI) / 180);
        c.scale(scale, scale);
        c.fillStyle = fill;
        c.strokeStyle = 墨;
        c.lineWidth = 5;
        c.fillRect(-w / 2, -h / 2, w, h);
        c.strokeRect(-w / 2, -h / 2, w, h);
        c.restore();
    }

    function 生成斑点(变体, 数量) {
        return Array.from({ length: 数量 }, () => ({
            x: Math.random(),
            y: Math.random(),
            size: 随机数(1.5, 5),
            speed: 随机数(.18, 1.2) * 变体.wave,
            phase: 随机数(0, Math.PI * 2),
            drift: 随机数(6, 34) * 变体.spread,
            color: 变体.colors[Math.floor(Math.random() * 变体.colors.length)],
        }));
    }

    function 绘制斑点(c, 斑点群, w, h, t, 秒数) {
        const visible = Math.sin(t * Math.PI);
        for (const 斑点 of 斑点群) {
            const x = (斑点.x * w + Math.cos(秒数 * 斑点.speed + 斑点.phase) * 斑点.drift + w) % w;
            const y = (斑点.y * h + Math.sin(秒数 * 斑点.speed + 斑点.phase) * 斑点.drift + h) % h;
            c.fillStyle = 透明色(斑点.color, .34 * visible);
            c.fillRect(x, y, 斑点.size, 斑点.size);
        }
    }

    function 随机数(min, max) {
        return min + Math.random() * (max - min);
    }

    function 按毫秒加速(ms) {
        return Math.max(0, Math.round(ms / 入口速度));
    }

    function 按秒加速(ms) {
        return 按毫秒加速(ms) / 1000;
    }

    function 生成变体(基础) {
        const 种子 = Math.random();
        const 偏移 = Math.floor(随机数(0, 基础.colors.length));
        const 调色板 = 轮转(基础.colors, 偏移);
        if (Math.random() > 0.55) {
            const 交换序号 = Math.floor(随机数(1, 调色板.length));
            [调色板[0], 调色板[交换序号]] = [调色板[交换序号], 调色板[0]];
        }
        const 算法 = ["radial", "diagonal", "grid", "spiral", "fold", "scatter"][Math.floor(随机数(0, 6))];
        const 轮廓 = {
            radial: { density: [0.88, 1.3], cell: [20, 34], spread: [0.9, 1.24] },
            diagonal: { density: [0.72, 1.08], cell: [24, 44], spread: [1.06, 1.42] },
            grid: { density: [1.0, 1.45], cell: [16, 30], spread: [0.82, 1.12] },
            spiral: { density: [0.86, 1.32], cell: [18, 36], spread: [1.0, 1.34] },
            fold: { density: [0.78, 1.12], cell: [28, 48], spread: [0.88, 1.18] },
            scatter: { density: [1.08, 1.52], cell: [18, 34], spread: [1.04, 1.44] },
        }[算法];
        const 网格 = {
            cols: Math.floor(随机数(7, 16)),
            rows: Math.floor(随机数(5, 11)),
            cell: 随机数(轮廓.cell[0], 轮廓.cell[1]),
        };
        const 角度 = 随机数(-34, 34);
        return {
            ...基础,
            colors: 调色板,
            调色板,
            算法: 算法,
            网格: 网格,
            density: 随机数(轮廓.density[0], 轮廓.density[1]),
            角度: 角度,
            angleRad: (角度 * Math.PI) / 180,
            种子: 种子,
            phase: 种子 * Math.PI * 2,
            wave: 随机数(0.76, 1.42),
            dot: 随机数(1.0, 3.2),
            size: 随机数(0.78, 1.26),
            spread: 随机数(轮廓.spread[0], 轮廓.spread[1]),
            rotation: 随机数(0.72, 1.45),
            pace: 随机数(0.82, 1.12),
        };
    }

    function 轮转(项列, 数量) {
        return 项列.slice(数量).concat(项列.slice(0, 数量));
    }

    function 缓出三次(t) {
        return 1 - Math.pow(1 - t, 3);
    }

    function 染色(hex, amount) {
        const rgb = 转色值(hex);
        return `rgb(${Math.round(rgb.r + (255 - rgb.r) * amount)}, ${Math.round(rgb.g + (255 - rgb.g) * amount)}, ${Math.round(rgb.b + (255 - rgb.b) * amount)})`;
    }

    function 透明色(hex, value) {
        const rgb = 转色值(hex);
        return `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${value})`;
    }

    function 转色值(hex) {
        const raw = hex.replace("#", "");
        const value = parseInt(raw, 16);
        return {
            r: (value >> 16) & 255,
            g: (value >> 8) & 255,
            b: value & 255,
        };
    }
})();
