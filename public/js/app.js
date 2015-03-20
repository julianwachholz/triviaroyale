(function (window, document) {

var WS_ADDR = 'ws' + (window.location.protocol === 'https:' ? 's' : '') + '://' + window.location.hostname + ':8765',
    ws = new ReconnectingWebSocket(WS_ADDR, null, {
        automaticOpen: false,
        maxReconnectAttempts: 5
    }),
    pingTimeout;

ws.addEventListener('open', function (event) {
    var playername, password;

    state.innerHTML = '<p>Connected! :)</p>';

    setTimeout(function () {
        state.classList.add('hidden');
        ws.send(JSON.stringify({ping: performance.now()}));
    }, 500);

    playername = localStorage.getItem('playername');
    if (playername) {
        password = localStorage.getItem('password');
        if (password) {
            ws.send(JSON.stringify({
                login: playername,
                password: password,
                auto: true
            }))
        } else {
            ws.send(JSON.stringify({login: playername}));
        }
    } else {
        window.modal('login');
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
    if (data.system) {
        chatMessage(data.system, true);
    }
    if (data.prompt) {
        window.modal(data.prompt, data.data);
    }
    if (data.setinfo) {
        for (key in data.setinfo) {
            document.getElementById(key).innerHTML = data.setinfo[key];
            if (key === 'playername') {
                localStorage.setItem('playername', data.setinfo[key]);
                chatinput.disabled = false;
                chatinput.focus();
            }
            if (key === 'timer') {
                animateTimer();
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

function modalPrompt(prompt, callback, allowEmpty) {
    var wasDisabled = chatinput.disabled;
    form.removeEventListener('submit', chatHandler);
    chatinput.disabled = false;
    chatinput.placeholder = prompt;
    chatinput.focus();
    chatMessage(prompt, true);
    form.addEventListener('submit', function modalHandler(event) {
        var value = chatinput.value;
        event.preventDefault();
        if (value || allowEmpty) {
            chatinput.placeholder = '';
            form.removeEventListener('submit', modalHandler);
            form.addEventListener('submit', chatHandler);
            if (wasDisabled) {
                chatinput.disabled = true;
            }
            callback(value);
        } else {
            alert("Please enter a value!");
        }
        chatinput.value = '';
    });
}

window.modal = function (which, data) {
    if (which === 'login') {
        modalPrompt('Please choose your player name!', function (name) {
            ws.send(JSON.stringify({login: name}));
        });
    }
    if (which === 'password') {
        modalPrompt('Enter password for ' + data.login + ':', function (password) {
            localStorage.setItem('password', password);
            data.password = password;
            ws.send(JSON.stringify(data));
        });
    }
};

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
        text = autolink(text);
    }
    message.innerHTML = '<span>' + text + '</span>';
    message.innerHTML += '<time>' + (now.getHours() < 10 ? '0' : '') + now.getHours() + ':'
                      + (now.getMinutes() < 10 ? '0' : '') + now.getMinutes() + ':'
                      + (now.getSeconds() < 10 ? '0' : '') + now.getSeconds() + '</time>';
    chat.appendChild(message);

    if (chat.scrollHeight - chat.scrollTop < 500) {
        chat.scrollTop = chat.scrollHeight;
    }
    if (chat.childElementCount > 100) {
        chat.removeChild(chat.childNodes[0]);
    }
}

function chatHandler(event) {
    event.preventDefault();
    if (chatinput.value.length > 0) {
        ws.send(JSON.stringify({text: chatinput.value}));
        chatinput.value = '';
    }
}

function autolink(text) {
    return text.replace(
        /\b(https?:\/\/[\-A-Z0-9+\u0026\u2019@#\/%?=()~_|!:,.;]*[\-A-Z0-9+\u0026@#\/%=~()_|])\b/ig,
        '<a href="$1" target="_blank">$1</a>'
    );
}
function escapeHTML(text) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(text));
    return div.innerHTML;
}

function animateTimer(timer) {
    var timerBar = document.querySelector('.timer-bar'),
        timerValue = document.querySelector('.timer-value span'),
        seconds;

    if (timerBar) {
        seconds = parseFloat(timerBar.getAttribute('data-time-left'));
        timerBar.style.transition = 'width ' + (seconds - 0.1) + 's linear, background ' + (seconds - 0.1) + 's linear';
        (function countdown(seconds) {
            if (seconds > 0) {
                timerValue.innerHTML = seconds.toFixed(1);
                setTimeout(function () { countdown(seconds - 0.1) }, 100);
            } else {
                timerValue.innerHTML = '0.0';
            }
        }(seconds));
        setTimeout(function () {
            timerBar.style.width = '0%';
            if (!timerBar.classList.contains('colorless')) {
                timerBar.style.backgroundColor = 'rgba(255,0,0,0.25)';
            }
        }, 100);
    }
}

document.addEventListener('DOMContentLoaded', function () {
    form.addEventListener('submit', chatHandler);
    playername.addEventListener('click', function (event) {
        event.preventDefault();
        modalPrompt('Change your player name!', function (name) {
            if (name) {
                ws.send(JSON.stringify({login: name}));
            }
        }, true);
    });
});

window.addEventListener('load', function () {
    body.classList.remove('loading');
});

window.addEventListener('keydown', function () {
    chatinput.focus();
});

})(window, document);
