(function (global) {
    'use strict';

    function 转义网页(文本) {
        return String(文本 ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function 安全地址(地址, 是否图片) {
        const 原始地址 = String(地址 || '').trim().replace(/^<|>$/g, '');
        if (!原始地址) return '';
        try {
            const 解析结果 = new URL(原始地址, 'http://mybiout.local/');
            const 允许协议 = 是否图片 ? ['http:', 'https:'] : ['http:', 'https:', 'mailto:'];
            if (!允许协议.includes(解析结果.protocol)) return '';
        } catch (e) {
            return '';
        }
        return 转义网页(原始地址);
    }

    function 行内Markdown(原文) {
        const 令牌 = [];
        const 保存 = 网页 => `\uE000${令牌.push(网页) - 1}\uE001`;
        let 文本 = String(原文 || '');

        文本 = 文本.replace(/`([^`\n]+)`/g, (_, 代码) => 保存(`<code>${转义网页(代码)}</code>`));
        文本 = 文本.replace(/!\[([^\]]*)\]\((?:<([^>]+)>|([^\s)]+))(?:\s+["'][^"']*["'])?\)/g,
            (_, 替代文本, 尖括号地址, 普通地址) => {
                const 地址 = 安全地址(尖括号地址 || 普通地址, true);
                return 地址
                    ? 保存(`<img src="${地址}" alt="${转义网页(替代文本)}" loading="lazy">`)
                    : 转义网页(替代文本);
            });
        文本 = 文本.replace(/\[([^\]]+)\]\((?:<([^>]+)>|([^\s)]+))(?:\s+["'][^"']*["'])?\)/g,
            (_, 标签, 尖括号地址, 普通地址) => {
                const 地址 = 安全地址(尖括号地址 || 普通地址, false);
                return 地址
                    ? 保存(`<a href="${地址}" target="_blank" rel="noopener noreferrer">${转义网页(标签)}</a>`)
                    : 转义网页(标签);
            });

        文本 = 转义网页(文本)
            .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
            .replace(/~~([^~\n]+)~~/g, '<del>$1</del>')
            .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
            .replace(/ {2,}\n/g, '<br>')
            .replace(/\n/g, ' ');

        return 文本.replace(/\uE000(\d+)\uE001/g, (_, 索引) => 令牌[Number(索引)] || '');
    }

    function 拆分表格行(行) {
        let 文本 = String(行 || '').trim();
        if (文本.startsWith('|')) 文本 = 文本.slice(1);
        if (文本.endsWith('|')) 文本 = 文本.slice(0, -1);
        const 单元格 = [];
        let 当前 = '';
        let 已转义 = false;
        for (const 字符 of 文本) {
            if (已转义) {
                当前 += 字符 === '|' ? '|' : `\\${字符}`;
                已转义 = false;
            } else if (字符 === '\\') {
                已转义 = true;
            } else if (字符 === '|') {
                单元格.push(当前.trim());
                当前 = '';
            } else {
                当前 += 字符;
            }
        }
        if (已转义) 当前 += '\\';
        单元格.push(当前.trim());
        return 单元格;
    }

    function 是表格分隔行(行) {
        const 单元格 = 拆分表格行(行);
        return 单元格.length > 0 && 单元格.every(格 => /^:?-{3,}:?$/.test(格));
    }

    function 渲染(原文) {
        const 行列表 = String(原文 || '').replace(/\r\n?/g, '\n').split('\n');
        const 网页片段 = [];
        let 段落 = [];

        function 输出段落() {
            if (!段落.length) return;
            网页片段.push(`<p>${行内Markdown(段落.join('\n'))}</p>`);
            段落 = [];
        }

        for (let 索引 = 0; 索引 < 行列表.length;) {
            const 行 = 行列表[索引];
            const 去空行 = 行.trim();

            if (!去空行) {
                输出段落();
                索引 += 1;
                continue;
            }

            const 代码围栏 = 去空行.match(/^```([^`]*)$/);
            if (代码围栏) {
                输出段落();
                const 代码行 = [];
                索引 += 1;
                while (索引 < 行列表.length && !/^```\s*$/.test(行列表[索引])) {
                    代码行.push(行列表[索引]);
                    索引 += 1;
                }
                if (索引 < 行列表.length) 索引 += 1;
                网页片段.push(`<pre><code>${转义网页(代码行.join('\n'))}</code></pre>`);
                continue;
            }

            const 标题 = 行.match(/^\s*(#{1,6})\s+(.+?)\s*$/);
            if (标题) {
                输出段落();
                const 层级 = 标题[1].length;
                网页片段.push(`<h${层级}>${行内Markdown(标题[2])}</h${层级}>`);
                索引 += 1;
                continue;
            }

            if (/^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/.test(行)) {
                输出段落();
                网页片段.push('<hr>');
                索引 += 1;
                continue;
            }

            if (索引 + 1 < 行列表.length && 行.includes('|') && 是表格分隔行(行列表[索引 + 1])) {
                输出段落();
                const 表头 = 拆分表格行(行);
                索引 += 2;
                const 表体 = [];
                while (索引 < 行列表.length && 行列表[索引].includes('|') && 行列表[索引].trim()) {
                    表体.push(拆分表格行(行列表[索引]));
                    索引 += 1;
                }
                let 表格网页 = '<table><thead><tr>' + 表头.map(格 => `<th>${行内Markdown(格)}</th>`).join('') + '</tr></thead>';
                if (表体.length) {
                    表格网页 += '<tbody>' + 表体.map(行数据 => '<tr>' + 表头.map((_, 列) => `<td>${行内Markdown(行数据[列] || '')}</td>`).join('') + '</tr>').join('') + '</tbody>';
                }
                网页片段.push(表格网页 + '</table>');
                continue;
            }

            if (/^\s*>\s?/.test(行)) {
                输出段落();
                const 引用行 = [];
                while (索引 < 行列表.length && /^\s*>\s?/.test(行列表[索引])) {
                    引用行.push(行列表[索引].replace(/^\s*>\s?/, ''));
                    索引 += 1;
                }
                网页片段.push(`<blockquote>${引用行.map(行文本 => 行内Markdown(行文本)).join('<br>')}</blockquote>`);
                continue;
            }

            const 列表项 = 行.match(/^\s*([-+*]|\d+[.)])\s+(.+)$/);
            if (列表项) {
                输出段落();
                const 有序 = /^\d/.test(列表项[1]);
                const 标签 = 有序 ? 'ol' : 'ul';
                const 项目 = [];
                while (索引 < 行列表.length) {
                    const 匹配 = 行列表[索引].match(/^\s*([-+*]|\d+[.)])\s+(.+)$/);
                    if (!匹配 || /^\d/.test(匹配[1]) !== 有序) break;
                    项目.push(`<li>${行内Markdown(匹配[2])}</li>`);
                    索引 += 1;
                }
                网页片段.push(`<${标签}>${项目.join('')}</${标签}>`);
                continue;
            }

            段落.push(行);
            索引 += 1;
        }

        输出段落();
        return 网页片段.join('\n');
    }

    global.MyBiOutMarkdown = Object.freeze({ render: 渲染 });
})(window);
