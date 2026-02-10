// Theme toggle — light default, dark opt-in, persisted to localStorage
(function () {
    const toggle = document.getElementById('theme-toggle');
    if (!toggle) return;

    toggle.addEventListener('click', function () {
        const isDark = document.documentElement.classList.toggle('dark');
        localStorage.setItem('theme', isDark ? 'dark' : 'light');
        var tc = document.getElementById('theme-color');
        if (tc) tc.content = isDark ? '#000000' : '#ffffff';
    });
})();
