(function (window, document) {

var chat = null;
var ws = new ReconnectingWebSocket('ws://localhost:8765', null, {
    automaticOpen: false
});

ws.addEventListener('open', function (event) {
    console.info('ws opened', event);
});
ws.addEventListener('connecting', function (event) {
    console.info('connecting', event);
});
ws.addEventListener('close', function (event) {
    console.warn('ws closed', event);
});
ws.addEventListener('error', function (event) {
    console.error('error', event);
});
ws.addEventListener('message', function (message) {
    var data = JSON.parse(message.data);
    console.log('message', data);

    if (data.text) {
        chat.innerHTML += '<div class="message">' + data.text + '</div>';
        chat.scrollTop = chat.scrollHeight;
    }
});

ws.open();

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
