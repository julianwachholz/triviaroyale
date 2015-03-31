(function (window, document) {

var WS_ADDR = 'ws' + (window.location.protocol === 'https:' ? 's' : '') + '://' + window.location.hostname + ':8080',
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
    if (data instanceof Array) {
        data.forEach(handleMessage);
    } else {
        handleMessage(data);
    }
});

function handleMessage(data) {
    if (data.pong) {
        checkLatency(data.pong);
    }
    if (data.player && data.text) {
        chatMessage(data.player + ': ' + data.text, false, data.time);
    }
    if (data.system) {
        chatMessage(data.system, true, null, data.system_extra);
    }
    if (data.prompt) {
        window.modal(data.prompt, data.data);
    }
    if (data.setinfo) {
        for (key in data.setinfo) {
            document.getElementById(key).innerHTML = data.setinfo[key];
            if (key === 'playername') {
                changename.innerHTML = 'Change name';
                changepassword.classList.remove('hidden');
                localStorage.setItem('playername', data.setinfo[key]);
                chatinput.disabled = false;
                chatinput.focus();
            }
            if (key === 'timer') {
                animateTimer();
            }
        }
    }
}

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

function modalPrompt(prompt, options, callback) {
    var wasDisabled = chatinput.disabled;
    form.removeEventListener('submit', chatHandler);
    if (options.hasOwnProperty('max')) {
        chatinput.maxLength = options.max;
    }
    chatinput.disabled = false;
    chatinput.placeholder = prompt;
    chatinput.focus();
    chatMessage(prompt, true);
    form.addEventListener('submit', function modalHandler(event) {
        var value = chatinput.value;
        event.preventDefault();
        if (value || options.hasOwnProperty('allowEmpty') && options.allowEmpty) {
            chatinput.placeholder = '';
            chatinput.maxLength = 250;
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
        modalPrompt('Please choose your player name!', {max: 40}, function (name) {
            ws.send(JSON.stringify({login: name}));
        });
    }
    if (which === 'password') {
        if (!data || !data.login) {
            console.warn('modal password without login called');
            return;
        }
        modalPrompt('Enter password for ' + data.login + ':', {}, function (password) {
            localStorage.setItem('password', password);
            data.password = password;
            ws.send(JSON.stringify(data));
        });
    }
};

/**
 * rate the previous question if possible.
 */
window.vote = function (updown) {
    ws.send(JSON.stringify({command: 'vote', vote: updown}));
};

/**
 * append a chat message
 */
function chatMessage(text, system, time, extra) {
    var message = document.createElement('p'),
        tstamp = new Date();
    if (system) {
        message.classList.add('system');
        text = '<strong>Trivia:</strong> ' + formatText(escapeHTML(text));
        if (!!extra) {
            text +=  ' ' + extra;
        }
    } else {
        text = escapeHTML(text);
        text = autolink(text);
        if (!!time) {
            tstamp = new Date(1000 * time);
        }
    }
    message.innerHTML = '<span>' + text + '</span>';
    message.innerHTML += '<time>' + (tstamp.getHours() < 10 ? '0' : '') + tstamp.getHours() + ':'
                      + (tstamp.getMinutes() < 10 ? '0' : '') + tstamp.getMinutes() + ':'
                      + (tstamp.getSeconds() < 10 ? '0' : '') + tstamp.getSeconds() + '</time>';
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
function formatText(text) {
    return text.replace(
        /\*([^\*]+)\*/ig,
        '<b>$1</b>'
    );
}
function escapeHTML(text) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(text));
    return div.innerHTML;
}

function animateTimer() {
    var timerBar = document.querySelector('.timer-bar'),
        timerValue = document.querySelector('.timer-value span'),
        COLOR_START = [0, 255, 0, 0.25],
        COLOR_END = [255, 0, 0, 0.25],
        timeTotal, timeLeft, timeout = 0.1;

    if (timerBar) {
        timeTotal = parseFloat(timerBar.getAttribute('data-total-time'));
        timeLeft = parseFloat(timerBar.getAttribute('data-time-left'));

        if (!timerBar.classList.contains('colorless')) {
            timerBar.style.backgroundColor = gradient(COLOR_START, COLOR_END, timeLeft / timeTotal);
        }
        timerBar.style.transition = 'width ' + (timeLeft - timeout) + 's linear, background ' + (timeLeft - 0.1) + 's linear';

        (function countdown(timeLeft) {
            if (timeLeft > 0) {
                timerValue.innerHTML = timeLeft.toFixed(1);
                setTimeout(function () { countdown(timeLeft - timeout) }, 100);
            } else {
                timerValue.innerHTML = '0.0';
            }
        }(timeLeft));

        setTimeout(function () {
            timerBar.style.width = '0%';
            if (!timerBar.classList.contains('colorless')) {
                timerBar.style.backgroundColor = rgba(COLOR_END);
            }
        }, timeout * 1000);
    }
}

function gradient(from, to, percent) {
    var r = parseInt(to[0] + percent * (from[0] - to[0])),
        g = parseInt(to[1] + percent * (from[1] - to[1])),
        b = parseInt(to[2] + percent * (from[2] - to[2])),
        a = to[3] + percent * (from[3] - to[3]);
    return rgba([r,g,b,a]);
}
function rgba(rgba) {
    return 'rgba('+rgba[0]+','+rgba[1]+','+rgba[2]+','+rgba[3]+')';
}

function inputHistory(max_history) {
    var PREV = 38, NEXT = 40, ENTER = 13,
        history = [''], current = 0;

    if (!max_history) {
        max_history = 100;
    }

    return function (event) {
        switch (event.which) {
            case ENTER:
            if (this.value.trim().length > 0) {
                history[current] = this.value;
                history.unshift('');
                current = 0;
                if (history.length > max_history) {
                    history = history.slice(0, max_history);
                }
            }
            break;

            case PREV:
            if (current + 1 < history.length) {
                event.preventDefault();
                history[current] = this.value;
                current += 1;
                this.value = history[current];
            }
            break;

            case NEXT:
            if (current - 1 >= 0) {
                event.preventDefault();
                history[current] = this.value;
                current -= 1;
                this.value = history[current];
            }
            break;
        }
    };
}

document.addEventListener('DOMContentLoaded', function () {
    form.addEventListener('submit', chatHandler);
    chatinput.addEventListener('keydown', inputHistory());

    menu.addEventListener('click', function (event) {
        event.preventDefault();
        this.classList.toggle('open');
        aside.classList.toggle('open');
    });

    changename.addEventListener('click', function (event) {
        event.preventDefault();
        menu.classList.toggle('open');
        aside.classList.toggle('open');
        modalPrompt('Change your player name!', {allowEmpty: true, max: 40}, function (name) {
            if (name) {
                ws.send(JSON.stringify({login: name}));
            }
        });
    });
    changepassword.addEventListener('click', function (event) {
        var playername;
        event.preventDefault();
        menu.classList.toggle('open');
        aside.classList.toggle('open');

        playername = localStorage.getItem('playername');
        if (playername) {
            window.modal('password', {login: playername});
        }
    });
});

window.addEventListener('load', function () {
    body.classList.remove('loading');
});

window.addEventListener('keydown', function () {
    chatinput.focus();
});

})(window, document);
