(function (global) {
    async function 解析并构建(文本) {
        const r = await (await fetch('/api/parse-batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: 文本 })
        })).json();
        return r;
    }

    function 挂载批量输入(选项) {
        const 单行 = document.getElementById(选项.inputId);
        const 多行 = document.getElementById(选项.textareaId);
        const 加号 = document.getElementById(选项.toggleId);
        const 计数 = 选项.countId ? document.getElementById(选项.countId) : null;
        let 展开 = false;

        function 当前文本() {
            return (展开 ? 多行.value : 单行.value);
        }

        function 设文本(v) {
            单行.value = v;
            多行.value = v;
            if (计数 && !String(v || '').trim()) 计数.textContent = '';
        }

        function 设展开(on) {
            展开 = !!on;
            单行.style.display = 展开 ? 'none' : '';
            多行.style.display = 展开 ? '' : 'none';
            加号.textContent = 展开 ? '−' : '+';
            加号.title = 展开 ? '收起为单行' : '展开多行输入';
            加号.setAttribute('aria-expanded', 展开 ? 'true' : 'false');
            if (展开) 多行.focus();
            else 单行.focus();
        }

        async function 自动构建() {
            const v = 当前文本();
            if (!String(v || '').trim()) {
                if (计数) 计数.textContent = '';
                return { items: [] };
            }
            const r = await 解析并构建(v);
            const items = r.items || [];
            if (items.length > 1) {
                const built = r.built || items.join('\n');
                多行.value = built;
                单行.value = items.join(' ');
                if (!展开) 设展开(true);
            }
            if (计数) 计数.textContent = items.length ? ('已识别 ' + items.length + ' 条') : '';
            return r;
        }

        加号.addEventListener('click', function () {
            if (!展开) {
                多行.value = 单行.value;
                设展开(true);
                自动构建();
            } else {
                单行.value = 多行.value.split(/\s+/).filter(Boolean).join(' ');
                设展开(false);
            }
        });

        单行.addEventListener('paste', function () { setTimeout(自动构建, 0); });
        多行.addEventListener('paste', function () { setTimeout(自动构建, 0); });
        多行.addEventListener('blur', function () { 自动构建(); });
        多行.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                if (选项.onSubmit) 选项.onSubmit();
            }
        });

        return { 当前文本: 当前文本, 设文本: 设文本, 自动构建: 自动构建, 是否展开: function () { return 展开; }, 设展开: 设展开 };
    }

    global.挂载批量输入 = 挂载批量输入;
})(window);
