document.addEventListener('keydown', function (event) {
    if (event.key === '/' && ['INPUT', 'TEXTAREA'].indexOf(document.activeElement.tagName) === -1) {
        event.preventDefault();
        var target = document.querySelector('[data-slash-focus]');
        if (target) target.focus();
    }
});
