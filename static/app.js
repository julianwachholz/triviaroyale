(function (window, document) {
/**
 * chat client
 */
var chat = null;

var ws = new ReconnectingWebSocket('ws://' + window.location.host + '/ws');

ws.addEventListener('message', function (message) {
    var data = JSON.parse(message.data);
    chat.innerHTML += '<div class="message">' + data.text + '</div>';
    chat.scrollTop = chat.scrollHeight;
});

document.addEventListener('DOMContentLoaded', function () {
    var form = document.getElementById('form');
    var input = document.getElementById('input');
    chat = document.getElementById('chat');

    form.addEventListener('submit', function (event) {
        event.preventDefault();
        ws.send(JSON.stringify({text: input.value}));
        input.value = '';
    });
});

})(window, document);
