(function (window, document) {
'use strict';

var TIMER_COLOR_START = [76, 175, 80, 0.5],  // #4caf50
    TIMER_COLOR_END = [244, 67, 54, 0.5],    // #f44336
    PING_FREQ = 5000;

var ws = new ReconnectingWebSocket(WS_ADDR, null, {
        automaticOpen: false,
        maxReconnectAttempts: 10
    }),
    playerList = [],
    pingTimeout,
    modalTimeout,
    timerTimeout;

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
    clearTimeout(timerTimeout);
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
        chatMessage({
            player: data.player,
            text: data.text,
            time: data.time
        });
    }
    if (data.system) {
        chatMessage({
            system: true,
            announce: !!data.announce,
            text: data.system,
            unescaped: data.system_extra
        });
    }
    if (data.prompt) {
        window.showModal(data.prompt, data.data);
    }
    if (data.setinfo) {
        for (var key in data.setinfo) {
            if (key === 'players') {
                updatePlayers(data.setinfo[key]);
                continue;
            }

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

function updatePlayers(players) {
    var html = '', i;
    for (i = 0; i < players.length; i += 1) {
        html += '<li><a onclick="showModal(\'ajax\', \'/stats/user/?name=' + players[i] + '\')">' + players[i] + '</a></li>';
    }
    playerlist.innerHTML = html;
    playerList = players;
}

window.showModal = function(modalId, data) {
    modalform.classList.remove('hidden');
    modalclose.classList.add('hidden');

    switch (modalId) {
        case 'welcome':
            modalcommand.value = 'login';
            modaltext.innerHTML = '<h2>Welcome to Trivia!</h2><p>Please choose your player name below.</p>';
            modalinputs.innerHTML = '<div class="form-input">' +
                    '<input type="text" name="login" id="login" maxlength="30" autofocus required>' +
                    '<label for="login">Nickname</label></div>';
            modalcancel.classList.add('hidden');
            modalsubmit.innerHTML = 'Login';
            break;

        case 'login':
            modalcommand.value = 'login';
            modaltext.innerHTML = '<h2>Change player name</h2>';
            modalinputs.innerHTML = '<div class="form-input">' +
                    '<input type="text" name="login" id="login" maxlength="30" required>' +
                    '<label for="login">Nickname</label></div>';
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
            modalinputs.innerHTML = '<div class="form-input">' +
                    '<input type="password" name="password" id="password" '+(!!data.auto ? 'autofocus' : '')+' required>' +
                    '<label for="password">Password</label></div>' +
                    '<div class="form-checkbox">' +
                        '<input type="checkbox" name="rememberme" id="rememberme">' +
                        '<label for="rememberme">Save password?</label>' +
                    '</div>' +
                    '<input type="hidden" name="login" value="'+escapeHTML(data.login)+'">';
            break;

        case 'ajax':
            modalclose.classList.remove('hidden');
            modalform.classList.add('hidden');
            modaltext.innerHTML = '<h2>Loading...</h2>' +
                '<div class="progress"><div class="indeterminate"></div></div>';
            ajax(data, null, function (result) {
                modaltext.innerHTML = result;
            });
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

window.ajaxForm = function (event, form) {
    event.preventDefault();

    modaltext.innerHTML = '<h2>Loading...</h2>' +
        '<div class="progress"><div class="indeterminate"></div></div>';

    ajax(form.action, new FormData(form), function (result) {
        modaltext.innerHTML = result;
    });
};


function command(cmd, args) {
    ws.send(JSON.stringify({
        command: cmd, args: args
    }));
}
window.command = command;


function ajax(url, data, cb) {
    var request = new XMLHttpRequest();
    request.open(!!data ? 'POST' : 'GET', url, true);

    request.onload = function() {
      if (this.status >= 200 && this.status < 400) {
        cb(this.response);
      } else {
        console.error('Got error response from server :(');
      }
    };
    request.onerror = function() {
        console.error('Something went wrong with this request.');
    };

    if (!!data) {
        request.send(data);
    } else {
        request.send();
    }
}

/**
 * append a chat message
 */
function chatMessage(opts) {
    var message = document.createElement('p'),
        tstamp = new Date(),
        text;

    if (opts.system) {
        message.classList.add('system');
        if (opts.announce) {
            message.classList.add('announce');
            text = '<hr /><span><em>' + formatText(escapeHTML(opts.text)) + '</em></span>';
        } else {
            text = '<strong>Trivia:</strong> ' + formatText(escapeHTML(opts.text));
            if (!!opts.unescaped) {
                text +=  ' ' + opts.unescaped;
            }
        }
    } else {
        text = formatText(escapeHTML(opts.player + ': ' + opts.text));
        if (!!opts.time) {
            tstamp = new Date(1000 * opts.time);
        }
    }
    message.innerHTML = '<span>' + text + '</span>';

    if (!opts.announce) {
        message.innerHTML += '<time>' + (tstamp.getHours() < 10 ? '0' : '') + tstamp.getHours() + ':' +
                             (tstamp.getMinutes() < 10 ? '0' : '') + tstamp.getMinutes() + ':' +
                             (tstamp.getSeconds() < 10 ? '0' : '') + tstamp.getSeconds() + '</time>';
    }

    chat.appendChild(message);

    if (chat.scrollHeight - chat.scrollTop < 500) {
        chat.scrollTop = chat.scrollHeight;
    }
    if (chat.childElementCount > 100) {
        chat.removeChild(chat.childNodes[0]);
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
        timeTotal, timeLeft, timeEnd, timeout = 0.1;

    if (timerBar) {
        timeTotal = parseFloat(timerBar.getAttribute('data-total-time'));
        timeLeft = parseFloat(timerBar.getAttribute('data-time-left'));
        timeEnd = new Date();
        timeEnd.setMilliseconds(timeEnd.getMilliseconds() + timeLeft * 1000);

        if (!timerBar.classList.contains('colorless')) {
            timerBar.style.backgroundColor = gradient(TIMER_COLOR_START, TIMER_COLOR_END, timeLeft / timeTotal);
        }
        timerBar.style.transition = 'width ' + (timeLeft - timeout) + 's linear, background-color ' + (timeLeft - 0.1) + 's linear';

        (function countdown() {
            var s = (timeEnd - new Date()) / 1000;
            if (s > 0 && timer.childNodes.length) {
                timerValue.innerHTML = s.toFixed(1);
                timerTimeout = setTimeout(countdown, timeout * 1000);
            } else {
                timerValue.innerHTML = '0.0';
            }
        }());

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
function rgba(val) {
    return 'rgba('+val[0]+','+val[1]+','+val[2]+','+val[3]+')';
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
    form.addEventListener('submit', function (event) {
        event.preventDefault();
        if (chatinput.value.length > 0) {
            ws.send(JSON.stringify({text: chatinput.value}));
            chatinput.value = '';
        }
    });
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

        // Remember password
        if (!!args.rememberme && args.rememberme) {
            console.info("remembering password");
            localStorage.setItem('password', args.password);
        }
        window.command(modalcommand.value, args);

        modal.classList.remove('show');
        modalTimeout = setTimeout(function () {
            modal.classList.add('hidden');
        }, 200);
    });
    var modalCancelFn = function (event) {
        event.preventDefault();
        modal.classList.remove('show');
        modalTimeout = setTimeout(function () {
            modal.classList.add('hidden');
        }, 200);
    };
    modalcancel.addEventListener('click', modalCancelFn);
    modalclose.addEventListener('click', modalCancelFn);
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
