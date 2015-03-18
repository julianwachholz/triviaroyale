(function (window, document) {

var ws = new ReconnectingWebSocket('ws://'+window.location.host+':8765', null, {
    automaticOpen: false,
    maxReconnectAttempts: 5
});
var pingTimeout;

ws.addEventListener('open', function (event) {
    state.innerHTML = '<p>Connected! :)</p>';

    setTimeout(function () {
        state.classList.add('hidden');
        ws.send(JSON.stringify({ping: performance.now()}));
    }, 500);

    var name = localStorage.getItem('playername');
    if (name) {
        ws.send(JSON.stringify({login: name}));
    } else {
        modalPrompt('Please choose your player name!', function (name) {
            ws.send(JSON.stringify({login: name}));
        });
    }
});
ws.addEventListener('connecting', function (event) {
    state.innerHTML = '<p>Connecting...</p>';
});
ws.addEventListener('close', function (event) {
    state.classList.remove('hidden');
    state.innerHTML = '<p>Connection lost! :(</p>';
    clearTimeout(pingTimeout);
});
ws.addEventListener('error', function (event) {
    state.classList.remove('hidden');
    state.innerHTML = '<p>Something went wrong! :(</p>';
});
ws.addEventListener('message', function (message) {
    var data = JSON.parse(message.data);

    if (data.pong) {
        checkLatency(data.pong);
    }
    if (data.player && data.text) {
        chatMessage(data.player + ': ' + data.text);
    }
    if (data.setinfo) {
        for (key in data.setinfo) {
            document.getElementById(key).innerHTML = data.setinfo[key];
            if (key === 'playername') {
                localStorage.setItem('playername', data.setinfo[key]);
                chatMessage('Welcome, <b>'+data.setinfo[key]+'</b>! Have fun playing Trivia!', true);
                chatinput.disabled = false;
                chatinput.focus();
            }
        }
    }
});

ws.open();

/**
 * latency is king in a quiz game, gotta have a better connection than the others!
 */
function checkLatency(time) {
    var latency;
    if (time) {
        latency = (performance.now() - time).toFixed(2);
        ping.innerHTML = latency.toString() + 'ms';
    }
    pingTimeout = setTimeout(function () {
        ws.send(JSON.stringify({ping: performance.now()}));
    }, 5000);
}

function modalPrompt(prompt, callback) {
    form.removeEventListener('submit', chatHandler);
    chatinput.disabled = false;
    chatinput.placeholder = prompt;
    chatinput.focus();
    chatMessage(prompt, true);
    form.addEventListener('submit', function modalHandler(event) {
        var value = chatinput.value;
        event.preventDefault();
        if (value) {
            chatinput.placeholder = '';
            form.removeEventListener('submit', modalHandler);
            form.addEventListener('submit', chatHandler);
            chatinput.disabled = true;
            callback(value);
        } else {
            alert("Please enter a value!");
        }
        chatinput.value = '';
    });
}

/**
 * append a chat message
 */
function chatMessage(text, system) {
    var message = document.createElement('p'), now = new Date();
    if (system) {
        message.classList.add('system');
        text = '<strong>System:</strong> ' + text;
    } else {
        text = escapeHTML(text);
    }
    message.innerHTML = '<span>' + text + '</span>';
    message.innerHTML += '<time>' + (now.getHours() < 10 ? '0' : '') + now.getHours() + ':'
                      + (now.getMinutes() < 10 ? '0' : '') + now.getMinutes() + ':'
                      + (now.getSeconds() < 10 ? '0' : '') + now.getSeconds() + '</time>';
    chat.appendChild(message);
    chat.scrollTop = chat.scrollHeight;
}

function chatHandler(event) {
    event.preventDefault();
    ws.send(JSON.stringify({text: chatinput.value}));
    chatinput.value = '';
}

function escapeHTML(text) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(text));
    return div.innerHTML;
}

document.addEventListener('DOMContentLoaded', function () {
    form.addEventListener('submit', chatHandler);
    playername.addEventListener('click', function (event) {
        event.preventDefault();
        modalPrompt('Change your player name!', function (name) {
            ws.send(JSON.stringify({login: name}));
        });
    });
});

window.addEventListener('load', function () {
    body.classList.remove('loading');
});

})(window, document);
