(function () {
    var cropper = null;
    var fileInput = document.getElementById('id_avatar');
    var cropArea = document.getElementById('crop-area');
    var cropImg = document.getElementById('crop-preview-img');

    fileInput.addEventListener('change', function () {
        var file = fileInput.files[0];
        if (!file) {
            cropArea.classList.add('hidden');
            if (cropper) { cropper.destroy(); cropper = null; }
            return;
        }
        var reader = new FileReader();
        reader.onload = function (ev) {
            if (cropper) { cropper.destroy(); cropper = null; }
            cropArea.classList.remove('hidden');
            cropImg.src = ev.target.result;
            requestAnimationFrame(function () {
                cropper = new Cropper(cropImg, {
                    aspectRatio: 1,
                    viewMode: 1,
                    autoCropArea: 0.9,
                    zoomable: false,
                    scalable: false,
                    movable: true,
                    guides: true,
                    background: false,
                    cropBoxMovable: true,
                    cropBoxResizable: true,
                });
            });
        };
        reader.readAsDataURL(file);
    });

    document.getElementById('profile-form').addEventListener('submit', function () {
        if (cropper) {
            var d = cropper.getData(true);
            document.getElementById('id_crop_x').value = d.x;
            document.getElementById('id_crop_y').value = d.y;
            document.getElementById('id_crop_width').value = d.width;
        }
    });
}());
