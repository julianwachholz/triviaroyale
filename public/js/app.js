(function (window, document) {

var TIMER_COLOR_START = [76, 175, 80, 0.5],  // #4caf50
    TIMER_COLOR_END = [244, 67, 54, 0.5],    // #f44336
    PING_FREQ = 5000;


var WS_ADDR = 'ws' + (window.location.protocol === 'https:' ? 's' : '') + '://' + window.location.hostname + ':8080',
    ws = new ReconnectingWebSocket(WS_ADDR, null, {
        automaticOpen: false,
        maxReconnectAttempts: 10
    }),
    pingTimeout, modalTimeout;

ws.addEventListener('open', function (event) {
    var playername, password;

    pagestatus.innerHTML = '<p>Connected! :)</p>';

    setTimeout(function () {
        pagestatus.classList.add('hidden');
        ws.send(JSON.stringify({ping: performance.now()}));
    }, 500);

    playername = localStorage.getItem('playername');
    if (playername) {
        password = localStorage.getItem('password');
        if (password) {
            command('login', {
                login: playername,
                password: password,
                auto: true
            });
        } else {
            command('login', {login: playername});
        }
    } else {
        window.showModal('welcome');
    }
});
ws.addEventListener('connecting', function (event) {
    pagestatus.innerHTML = '<p>Connecting...</p>';
});
ws.addEventListener('close', function (event) {
    pagestatus.classList.remove('hidden');
    pagestatus.innerHTML = '<p>Connection lost! :(</p>';
    clearTimeout(pingTimeout);
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
        window.showModal(data.prompt, data.data);
    }
    if (data.setinfo) {
        for (key in data.setinfo) {
            document.getElementById(key).innerHTML = data.setinfo[key];
            if (key === 'playername') {
                // logged in successfully
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
        latency = (performance.now() - time);
        ping.innerHTML = latency.toFixed(3 - parseInt(Math.log10(latency))) + 'ms';
    }
    pingTimeout = setTimeout(function () {
        ws.send(JSON.stringify({ping: performance.now()}));
    }, PING_FREQ);
}


window.showModal = function(modalId, data) {
    switch (modalId) {
        case 'welcome':
            modalcommand.value = 'login';
            modaltext.innerHTML = '<h2>Welcome to Trivia!</h2><p>Please choose your player name below.</p>';
            modalinputs.innerHTML = '<div class="form-input"> \
                    <input type="text" name="login" id="login" maxlength="30" autofocus required> \
                    <label for="login">Nickname</label></div>';
            modalcancel.classList.add('hidden');
            modalsubmit.innerHTML = 'Login';
            break;
        case 'login':
            modalcommand.value = 'login';
            modaltext.innerHTML = '<h2>Change player name</h2>';
            modalinputs.innerHTML = '<div class="form-input"> \
                    <input type="text" name="login" id="login" maxlength="30" required> \
                    <label for="login">Nickname</label></div>';
            modalcancel.classList.remove('hidden');
            modalsubmit.innerHTML = 'Change name';
            break;
        case 'password':
            if (!data.login) {
                console.warn('Password modal requires a login.');
                return;
            }
            modalcommand.value = 'login';
            if (!!data.auto) {
                modaltext.innerHTML = '<h2>Password required</h2><p>Enter password for '+escapeHTML(data.login)+':</p>';
                modalsubmit.innerHTML = 'Login';
                modalcancel.classList.add('hidden');
            } else {
                modaltext.innerHTML = '<h2>Change your password</h2><p>Enter your desired password:</p>';
                modalsubmit.innerHTML = 'Change password';
                modalcancel.classList.remove('hidden');
            }
            modalinputs.innerHTML = '<div class="form-input"> \
                    <input type="password" name="password" id="password" '+(!!data.auto ? 'autofocus' : '')+' required> \
                    <label for="password">Password</label></div> \
                    <div class="form-checkbox">\
                        <input type="checkbox" name="rememberme" id="rememberme">\
                        <label for="rememberme">Save password?</label>\
                    </div>\
                    <input type="hidden" name="login" value="'+escapeHTML(data.login)+'">';
            break;
        default:
            console.warn('Unknown modal window.');
            return;
    }
    if (modalTimeout) {
        clearTimeout(modalTimeout);
    }
    modal.classList.remove('hidden');
    modal.classList.add('show');
};


function command(command, args) {
    ws.send(JSON.stringify({
        command: command, args: args
    }));
}
window.command = command;


/**
 * append a chat message
 */
function chatMessage(text, system, time, unescaped) {
    var message = document.createElement('p'),
        tstamp = new Date();
    if (system) {
        message.classList.add('system');
        text = '<strong>Trivia:</strong> ' + formatText(escapeHTML(text));
        if (!!unescaped) {
            text +=  ' ' + unescaped;
        }
    } else {
        text = formatText(escapeHTML(text));
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

function formatText(text) {
    return text.replace( // *bold* text
        /\*([^\*]+)\*/g,
        '<b>$1</b>'
    ).replace(
        /_([^_]+)_/ig,
        '<i>$1</i>'
    ).replace( // automatic links
        /\b(https?:\/\/[\-A-Z0-9+\u0026\u2019@#\/%?=()~_|!:,.;]*[\-A-Z0-9+\u0026@#\/%=~()_|])\b/ig,
        '<a href="$1" target="_blank">$1</a>'
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
        timeTotal, timeLeft, timeout = 0.1;

    if (timerBar) {
        timeTotal = parseFloat(timerBar.getAttribute('data-total-time'));
        timeLeft = parseFloat(timerBar.getAttribute('data-time-left'));

        if (!timerBar.classList.contains('colorless')) {
            timerBar.style.backgroundColor = gradient(TIMER_COLOR_START, TIMER_COLOR_END, timeLeft / timeTotal);
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
                timerBar.style.backgroundColor = rgba(TIMER_COLOR_END);
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
        aside.classList.toggle('open');
    });
    menu_close.addEventListener('click', function (event) {
        event.preventDefault();
        aside.classList.toggle('open');
    });

    changename.addEventListener('click', function (event) {
        event.preventDefault();
        window.showModal('login');
    });
    changepassword.addEventListener('click', function (event) {
        var playername;
        event.preventDefault();
        window.showModal('password', {login: localStorage.getItem('playername')});
    });

    modalform.addEventListener('submit', function (event) {
        var el, args = {};
        event.preventDefault();

        for (var i = 0; i < modalform.length; i += 1) {
            el = modalform[i];
            if (!!el.name && el.name !== 'command') {
                if (el.type === 'checkbox') {
                    args[el.name] = !!el.checked;
                } else {
                    args[el.name] = el.value;
                }
            }
        }
        console.log(args);
        if (!!args['rememberme'] && args.rememberme) {
            console.info("remembering password");
            localStorage.setItem('password', args['password']);
        }
        window.command(modalcommand.value, args);

        modal.classList.remove('show');
        modalTimeout = setTimeout(function () {
            modal.classList.add('hidden');
        }, 200);
    });

    modalcancel.addEventListener('click', function (event) {
        event.preventDefault();
        modal.classList.remove('show');
        modalTimeout = setTimeout(function () {
            modal.classList.add('hidden');
        }, 200);
    });
});

window.addEventListener('load', function () {
    body.classList.remove('hidden');
});

window.addEventListener('keydown', function (event) {
    if (!event.metaKey && !event.ctrlKey && modal.classList.contains('hidden')) {
        chatinput.focus();
    }
});

})(window, document);
