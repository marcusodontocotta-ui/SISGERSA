var Odontograma = (function() {
    var PRONTUARIO_ID = null;
    var CONDICOES = {
        normal:     { cor: '#4CAF50', label: 'Normal',        icone: '' },
        carie:      { cor: '#F44336', label: 'Cárie',         icone: '' },
        restauracao:{ cor: '#2196F3', label: 'Restauração',   icone: '' },
        extracao:   { cor: '#9E9E9E', label: 'Extração',      icone: '' },
        coroa:      { cor: '#FF9800', label: 'Coroa',         icone: '' },
        implante:   { cor: '#9C27B0', label: 'Implante',      icone: '' },
        protese:    { cor: '#00BCD4', label: 'Prótese',       icone: '' },
        ausente:    { cor: '#FFFFFF', label: 'Ausente',       icone: '' },
        fratura:    { cor: '#FF5722', label: 'Fratura',       icone: '' },
        mancha:     { cor: '#795548', label: 'Mancha',        icone: '' },
        desgaste:   { cor: '#FFC107', label: 'Desgaste',      icone: '' },
        mobilidade: { cor: '#E91E63', label: 'Mobilidade',    icone: '' },
        tratar:     { cor: '#3F51B5', label: 'A Tratar',      icone: '' },
        observar:   { cor: '#607D8B', label: 'Observar',      icone: '' },
        encaminhar: { cor: '#FF6F00', label: 'Encaminhar',    icone: '' },
        provisorio: { cor: '#009688', label: 'Provisório',    icone: '' }
    };

    var TOOTH_PATHS = {
        incisor: {
            viewBox: '0 0 40 70',
            outline: 'M8,5 C8,2 12,0 20,0 C28,0 32,2 32,5 L33,28 C33,32 30,35 28,38 L27,55 C26,62 24,68 20,70 C16,68 14,62 13,55 L12,38 C10,35 7,32 7,28 Z',
            shadow: 'M8,5 C8,2 12,0 20,0 C28,0 32,2 32,5 L33,28 C33,32 30,35 28,38 L27,55 C26,62 24,68 20,70 L20,70 C20,70 24,68 25,55 L26,38 C28,35 33,32 33,28 L33,28 L8,28 Z',
            highlight: 'M14,5 C14,3 16,2 20,2 C24,2 26,3 26,5 L27,20 C27,22 25,24 20,24 C15,24 13,22 13,20 Z',
            labels: [{x:20,y:68}]
        },
        canino: {
            viewBox: '0 0 42 72',
            outline: 'M10,4 C10,1 14,0 21,0 C28,0 32,1 32,4 L34,30 C34,34 31,38 29,42 L27,58 C25,65 23,70 21,72 C19,70 17,65 15,58 L13,42 C11,38 8,34 8,30 Z',
            shadow: 'M10,4 C10,1 14,0 21,0 C28,0 32,1 32,4 L34,30 C34,34 31,38 29,42 L27,58 C25,65 23,70 21,72 L21,72 C23,70 25,65 27,58 L29,42 C31,38 34,34 34,30 L34,30 L10,30 Z',
            highlight: 'M15,4 C15,2 18,1 21,1 C24,1 27,2 27,4 L28,22 C28,24 26,26 21,26 C16,26 14,24 14,22 Z',
            labels: [{x:21,y:70}]
        },
        premolar: {
            viewBox: '0 0 44 72',
            outline: 'M8,6 C8,2 14,0 22,0 C30,0 36,2 36,6 L38,24 C38,28 35,32 33,35 L32,50 C30,60 27,66 22,70 C17,66 14,60 12,50 L11,35 C9,32 6,28 6,24 Z',
            shadow: 'M8,6 C8,2 14,0 22,0 C30,0 36,2 36,6 L38,24 C38,28 35,32 33,35 L32,50 C30,60 27,66 22,70 L22,70 C27,66 30,60 32,50 L33,35 C35,32 38,28 38,24 L38,24 L8,24 Z',
            highlight: 'M14,6 C14,3 18,1 22,1 C26,1 30,3 30,6 L31,18 C31,20 28,22 22,22 C16,22 13,20 13,18 Z',
            occlusalLine: 'M12,24 C16,22 20,23 22,22 C24,23 28,22 32,24',
            labels: [{x:22,y:68}]
        },
        molar: {
            viewBox: '0 0 48 72',
            outline: 'M6,8 C6,3 12,0 24,0 C36,0 42,3 42,8 L44,22 C44,26 40,30 38,33 L37,48 C35,58 30,66 24,70 C18,66 13,58 11,48 L10,33 C8,30 4,26 4,22 Z',
            shadow: 'M6,8 C6,3 12,0 24,0 C36,0 42,3 42,8 L44,22 C44,26 40,30 38,33 L37,48 C35,58 30,66 24,70 L24,70 C30,66 35,58 37,48 L38,33 C40,30 44,26 44,22 L44,22 L6,22 Z',
            highlight: 'M14,8 C14,4 18,2 24,2 C30,2 34,4 34,8 L35,18 C35,20 30,22 24,22 C18,22 13,20 13,18 Z',
            occlusalLine: 'M10,22 C15,20 19,22 24,20 C29,22 33,20 38,22',
            occlusalCross: ['M24,10 L24,22', 'M14,16 L34,16'],
            labels: [{x:24,y:68}]
        }
    };

    var TOOTH_DEFS = [];
    var Q1 = [18,17,16,15,14,13,12,11];
    var Q2 = [21,22,23,24,25,26,27,28];
    var Q3 = [31,32,33,34,35,36,37,38];
    var Q4 = [48,47,46,45,44,43,42,41];

    function getToothType(num) {
        var pos = num % 10;
        if (pos === 1 || pos === 2) return 'incisor';
        if (pos === 3) return 'canino';
        if (pos === 4 || pos === 5) return 'premolar';
        return 'molar';
    }

    function getFaces(dente) {
        var pos = dente % 10;
        if (pos === 1 || pos === 2) return ['Vestibular', 'Incisal', 'Lingual', 'Mesial', 'Distal'];
        if (pos === 3) return ['Vestibular', 'Incisal', 'Lingual', 'Mesial', 'Distal'];
        return ['Vestibular', 'Oclusal', 'Lingual', 'Mesial', 'Distal', 'Cervical'];
    }

    function buildToothDefs() {
        TOOTH_DEFS = [
            { num: 18, type: 'molar', quad: 1, pos: 0 },
            { num: 17, type: 'molar', quad: 1, pos: 1 },
            { num: 16, type: 'molar', quad: 1, pos: 2 },
            { num: 15, type: 'premolar', quad: 1, pos: 3 },
            { num: 14, type: 'premolar', quad: 1, pos: 4 },
            { num: 13, type: 'canino', quad: 1, pos: 5 },
            { num: 12, type: 'incisor', quad: 1, pos: 6 },
            { num: 11, type: 'incisor', quad: 1, pos: 7 },
            { num: 21, type: 'incisor', quad: 2, pos: 0 },
            { num: 22, type: 'incisor', quad: 2, pos: 1 },
            { num: 23, type: 'canino', quad: 2, pos: 2 },
            { num: 24, type: 'premolar', quad: 2, pos: 3 },
            { num: 25, type: 'premolar', quad: 2, pos: 4 },
            { num: 26, type: 'molar', quad: 2, pos: 5 },
            { num: 27, type: 'molar', quad: 2, pos: 6 },
            { num: 28, type: 'molar', quad: 2, pos: 7 },
            { num: 48, type: 'molar', quad: 4, pos: 0 },
            { num: 47, type: 'molar', quad: 4, pos: 1 },
            { num: 46, type: 'molar', quad: 4, pos: 2 },
            { num: 45, type: 'premolar', quad: 4, pos: 3 },
            { num: 44, type: 'premolar', quad: 4, pos: 4 },
            { num: 43, type: 'canino', quad: 4, pos: 5 },
            { num: 42, type: 'incisor', quad: 4, pos: 6 },
            { num: 41, type: 'incisor', quad: 4, pos: 7 },
            { num: 31, type: 'incisor', quad: 3, pos: 0 },
            { num: 32, type: 'incisor', quad: 3, pos: 1 },
            { num: 33, type: 'canino', quad: 3, pos: 2 },
            { num: 34, type: 'premolar', quad: 3, pos: 3 },
            { num: 35, type: 'premolar', quad: 3, pos: 4 },
            { num: 36, type: 'molar', quad: 3, pos: 5 },
            { num: 37, type: 'molar', quad: 3, pos: 6 },
            { num: 38, type: 'molar', quad: 3, pos: 7 }
        ];
    }

    var estadoAtual = {};
    var historicoDatas = [];
    var selectedTooth = null;
    var selectedFace = null;
    var currentData = null;
    var isProfissional = false;

    var SVG_NS = 'http://www.w3.org/2000/svg';

    function svgEl(tag, attrs) {
        var el = document.createElementNS(SVG_NS, tag);
        if (attrs) {
            for (var k in attrs) {
                el.setAttribute(k, attrs[k]);
            }
        }
        return el;
    }

    function createDefs(svg) {
        var defs = svgEl('defs');

        var gradShadow = svgEl('linearGradient', { id: 'gradShadow', x1: '0', y1: '0', x2: '1', y2: '1' });
        var s1 = svgEl('stop', { offset: '0%', 'stop-color': '#000', 'stop-opacity': '0' });
        var s2 = svgEl('stop', { offset: '100%', 'stop-color': '#000', 'stop-opacity': '0.3' });
        gradShadow.appendChild(s1);
        gradShadow.appendChild(s2);
        defs.appendChild(gradShadow);

        var gradHi = svgEl('linearGradient', { id: 'gradHighlight', x1: '0', y1: '0', x2: '0.3', y2: '1' });
        var h1 = svgEl('stop', { offset: '0%', 'stop-color': '#fff', 'stop-opacity': '0.7' });
        var h2 = svgEl('stop', { offset: '100%', 'stop-color': '#fff', 'stop-opacity': '0' });
        gradHi.appendChild(h1);
        gradHi.appendChild(h2);
        defs.appendChild(gradHi);

        var glowFilter = svgEl('filter', { id: 'glowFilter', x: '-20%', y: '-20%', width: '140%', height: '140%' });
        var feBlur = svgEl('feGaussianBlur', { stdDeviation: '2', result: 'blur' });
        var feMerge = svgEl('feMerge');
        var fm1 = svgEl('feMergeNode', { in: 'blur' });
        var fm2 = svgEl('feMergeNode', { in: 'SourceGraphic' });
        feMerge.appendChild(fm1);
        feMerge.appendChild(fm2);
        glowFilter.appendChild(feBlur);
        glowFilter.appendChild(feMerge);
        defs.appendChild(glowFilter);

        Object.keys(CONDICOES).forEach(function(key) {
            if (key === 'normal') return;
            var cor = CONDICOES[key].cor;
            var grad = svgEl('linearGradient', { id: 'grad_' + key, x1: '0', y1: '0', x2: '1', y2: '1' });
            var gs1 = svgEl('stop', { offset: '0%', 'stop-color': cor, 'stop-opacity': '0.85' });
            var gs2 = svgEl('stop', { offset: '100%', 'stop-color': cor, 'stop-opacity': '1' });
            grad.appendChild(gs1);
            grad.appendChild(gs2);
            defs.appendChild(grad);
        });

        svg.appendChild(defs);
    }

    function createSVG() {
        var container = document.getElementById('odontogram-area');
        if (!container) return null;
        container.innerHTML = '';

        var svg = svgEl('svg', {
            viewBox: '0 0 820 420',
            class: 'odontogram-svg',
            id: 'odontogram-svg'
        });

        createDefs(svg);

        var divLine = svgEl('line', { x1: '0', y1: '208', x2: '820', y2: '208', stroke: '#ccc', 'stroke-width': '1', 'stroke-dasharray': '6,4' });
        svg.appendChild(divLine);

        var qLabels = [
            { text: 'Quadrante 2 (Superior Direito)', x: 200, y: 22 },
            { text: 'Quadrante 1 (Superior Esquerdo)', x: 620, y: 22 },
            { text: 'Quadrante 3 (Inferior Esquerdo)', x: 200, y: 410 },
            { text: 'Quadrante 4 (Inferior Direito)', x: 620, y: 410 }
        ];
        qLabels.forEach(function(ql) {
            var t = svgEl('text', { x: ql.x, y: ql.y, class: 'quadrant-label' });
            t.textContent = ql.text;
            svg.appendChild(t);
        });

        TOOTH_DEFS.forEach(function(def) {
            var pathData = TOOTH_PATHS[def.type];
            var toothWidth = 52;
            var startX = 0;
            var startY = 32;
            var mirror = false;

            if (def.quad === 1) {
                startX = 780 - (def.pos * toothWidth);
                startY = 32;
                mirror = true;
            } else if (def.quad === 2) {
                startX = 20 + (def.pos * toothWidth);
                startY = 32;
            } else if (def.quad === 3) {
                startX = 20 + (def.pos * toothWidth);
                startY = 230;
            } else if (def.quad === 4) {
                startX = 780 - (def.pos * toothWidth);
                startY = 230;
                mirror = true;
            }

            var g = svgEl('g', {
                class: 'tooth-group',
                'data-dente': def.num,
                transform: 'translate(' + startX + ',' + startY + ')' + (mirror ? ' scale(-1,1) translate(-48,0)' : '')
            });

            var outline = svgEl('path', { d: pathData.outline, class: 'tooth-outline' });
            g.appendChild(outline);

            var shadow = svgEl('path', { d: pathData.shadow, class: 'tooth-shadow' });
            g.appendChild(shadow);

            var highlight = svgEl('path', { d: pathData.highlight, class: 'tooth-highlight' });
            g.appendChild(highlight);

            if (pathData.occlusalLine) {
                var ocl = svgEl('path', { d: pathData.occlusalLine, fill: 'none', stroke: '#888', 'stroke-width': '0.8', opacity: '0.5' });
                g.appendChild(ocl);
            }
            if (pathData.occlusalCross) {
                pathData.occlusalCross.forEach(function(line) {
                    var cl = svgEl('path', { d: line, fill: 'none', stroke: '#888', 'stroke-width': '0.6', opacity: '0.4' });
                    g.appendChild(cl);
                });
            }

            var facesG = svgEl('g', { class: 'faces-layer' });
            var faces = getFaces(def.num);
            var faceAreas = getFaceAreas(def.type);
            faces.forEach(function(face, i) {
                var area = faceAreas[i];
                if (!area) return;
                var faceRect = svgEl('path', {
                    d: area,
                    class: 'face-zone',
                    'data-dente': def.num,
                    'data-face': face
                });
                faceRect.addEventListener('click', function(e) {
                    e.stopPropagation();
                    onFaceClick(def.num, face);
                });
                facesG.appendChild(faceRect);
            });
            g.appendChild(facesG);

            var label = svgEl('text', {
                x: pathData.labels[0].x,
                y: pathData.labels[0].y,
                class: 'tooth-label'
            });
            label.textContent = def.num;
            g.appendChild(label);

            g.addEventListener('click', function() {
                onToothClick(def.num);
            });

            svg.appendChild(g);
        });

        container.appendChild(svg);
        return svg;
    }

    function getFaceAreas(type) {
        switch (type) {
            case 'incisor':
                return [
                    'M10,10 L30,10 L30,28 L10,28 Z',
                    'M10,28 L30,28 L30,42 L10,42 Z',
                    'M12,42 L28,42 L27,60 L13,60 Z',
                    'M8,5 L10,5 L10,60 L8,58 Z',
                    'M30,5 L32,5 L32,58 L30,60 Z'
                ];
            case 'canino':
                return [
                    'M12,10 L32,10 L34,28 L10,28 Z',
                    'M10,28 L34,28 L33,44 L11,44 Z',
                    'M13,44 L31,44 L28,62 L16,62 Z',
                    'M8,5 L12,5 L10,62 L8,58 Z',
                    'M32,5 L35,5 L35,58 L33,62 Z'
                ];
            case 'premolar':
                return [
                    'M10,10 L34,10 L36,22 L8,22 Z',
                    'M8,22 L36,22 L35,38 L9,38 Z',
                    'M11,38 L33,38 L30,62 L14,62 Z',
                    'M6,6 L10,6 L8,62 L6,58 Z',
                    'M34,6 L38,6 L38,58 L36,62 Z'
                ];
            case 'molar':
                return [
                    'M10,10 L38,10 L42,20 L6,20 Z',
                    'M6,20 L42,20 L40,38 L8,38 Z',
                    'M10,38 L36,38 L32,64 L14,64 Z',
                    'M4,6 L10,6 L8,64 L4,60 Z',
                    'M38,6 L44,6 L44,60 L40,64 Z'
                ];
            default:
                return [];
        }
    }

    function onToothClick(dente) {
        selectedTooth = dente;
        selectedFace = null;
        document.querySelectorAll('.tooth-group').forEach(function(g) {
            g.classList.remove('selected');
        });
        var g = document.querySelector('.tooth-group[data-dente="' + dente + '"]');
        if (g) g.classList.add('selected');
        updateFaceModal(dente, null);
    }

    function onFaceClick(dente, face) {
        selectedTooth = dente;
        selectedFace = face;
        document.querySelectorAll('.face-zone').forEach(function(fz) {
            fz.classList.remove('active');
        });
        var fz = document.querySelector('.face-zone[data-dente="' + dente + '"][data-face="' + face + '"]');
        if (fz) fz.classList.add('active');
        updateFaceModal(dente, face);
    }

    function updateFaceModal(dente, face) {
        var modal = document.getElementById('modalOdontograma');
        if (!modal) return;
        var inputDente = modal.querySelector('#odonto-dente');
        var inputFace = modal.querySelector('#odonto-face');
        if (inputDente) inputDente.value = dente;
        if (inputFace) inputFace.value = face || '';
        var labelEl = modal.querySelector('#odonto-tooth-label');
        if (labelEl) {
            var faceText = face ? ' - ' + face : ' (dente inteiro)';
            labelEl.textContent = 'Dente ' + dente + faceText;
        }
    }

    function renderEstado() {
        var svg = document.getElementById('odontogram-svg');
        if (!svg) return;

        document.querySelectorAll('.tooth-group').forEach(function(g) {
            var dente = parseInt(g.getAttribute('data-dente'));
            var outline = g.querySelector('.tooth-outline');
            var label = g.querySelector('.tooth-label');
            outline.classList.remove('tooth-extracted');
            if (label) label.style.fill = '#333';

            var faceZones = g.querySelectorAll('.face-zone');
            faceZones.forEach(function(fz) { fz.style.fill = ''; fz.style.stroke = ''; });
        });

        for (var key in estadoAtual) {
            var reg = estadoAtual[key];
            var dente = reg.dente;
            var face = reg.face;
            var condicao = reg.condicao;
            var cor = CONDICOES[condicao] ? CONDICOES[condicao].cor : '#ccc';

            var g = svg.querySelector('.tooth-group[data-dente="' + dente + '"]');
            if (!g) continue;

            var outline = g.querySelector('.tooth-outline');
            var label = g.querySelector('.tooth-label');

            if (condicao === 'extracao' || condicao === 'ausente') {
                outline.classList.add('tooth-extracted');
                if (label) label.style.fill = '#bbb';
            } else if (face) {
                var fz = g.querySelector('.face-zone[data-face="' + face + '"]');
                if (fz) {
                    fz.style.fill = cor;
                    fz.style.stroke = '#333';
                    fz.style.strokeWidth = '1';
                    fz.style.opacity = '0.85';
                }
            } else {
                outline.style.fill = cor;
            }
        }
    }

    function showTooltip(e, html) {
        var tt = document.getElementById('odontogram-tooltip');
        if (!tt) return;
        tt.innerHTML = html;
        tt.classList.add('show');
        tt.style.left = (e.pageX + 12) + 'px';
        tt.style.top = (e.pageY - 10) + 'px';
    }

    function hideTooltip() {
        var tt = document.getElementById('odontogram-tooltip');
        if (tt) tt.classList.remove('show');
    }

    function setupTooltips() {
        document.querySelectorAll('.face-zone').forEach(function(fz) {
            fz.addEventListener('mouseenter', function(e) {
                var dente = parseInt(fz.getAttribute('data-dente'));
                var face = fz.getAttribute('data-face');
                var key = dente + '_' + face;
                var reg = estadoAtual[key];
                var condLabel = reg ? (CONDICOES[reg.condicao] ? CONDICOES[reg.condicao].label : reg.condicao) : 'Normal';
                var html = '<span class="tooltip-condicao">' + condLabel + '</span>' +
                           '<span class="tooltip-info">Dente ' + dente + ' - ' + face + '</span>';
                if (reg && reg.observacoes) html += '<br><span class="tooltip-info">' + reg.observacoes + '</span>';
                showTooltip(e, html);
            });
            fz.addEventListener('mousemove', function(e) {
                var tt = document.getElementById('odontogram-tooltip');
                if (tt) {
                    tt.style.left = (e.pageX + 12) + 'px';
                    tt.style.top = (e.pageY - 10) + 'px';
                }
            });
            fz.addEventListener('mouseleave', hideTooltip);
        });

        document.querySelectorAll('.tooth-group').forEach(function(g) {
            g.addEventListener('mouseenter', function(e) {
                var dente = parseInt(g.getAttribute('data-dente'));
                var items = [];
                for (var key in estadoAtual) {
                    if (estadoAtual[key].dente === dente) {
                        items.push(estadoAtual[key]);
                    }
                }
                if (items.length === 0) return;
                var html = '<span class="tooltip-condicao">Dente ' + dente + '</span>';
                items.forEach(function(item) {
                    var faceText = item.face ? ' - ' + item.face : ' (geral)';
                    var condLabel = CONDICOES[item.condicao] ? CONDICOES[item.condicao].label : item.condicao;
                    html += '<br><span class="tooltip-info">' + faceText + ': ' + condLabel + '</span>';
                });
                showTooltip(e, html);
            });
            g.addEventListener('mousemove', function(e) {
                var tt = document.getElementById('odontogram-tooltip');
                if (tt) {
                    tt.style.left = (e.pageX + 12) + 'px';
                    tt.style.top = (e.pageY - 10) + 'px';
                }
            });
            g.addEventListener('mouseleave', hideTooltip);
        });
    }

    function loadEstado(data) {
        var url = '/api/odontograma/' + PRONTUARIO_ID + '/estado';
        if (data) url += '?data=' + data;
        return fetch(url)
            .then(function(r) { return r.json(); })
            .then(function(items) {
                estadoAtual = {};
                items.forEach(function(item) {
                    var key = item.dente + '_' + (item.face || 'geral');
                    estadoAtual[key] = item;
                });
                renderEstado();
                renderRecordsTable();
            });
    }

    function loadHistorico() {
        return fetch('/api/odontograma/' + PRONTUARIO_ID + '/historico')
            .then(function(r) { return r.json(); })
            .then(function(datas) {
                historicoDatas = datas;
                setupTimeline();
            });
    }

    function setupTimeline() {
        var container = document.getElementById('odontogram-timeline');
        if (!container) return;
        if (historicoDatas.length === 0) {
            container.innerHTML = '<div class="text-muted text-center py-2" style="font-size:0.8rem;">Nenhum registro</div>';
            return;
        }

        var dates = historicoDatas.map(function(d) { return d.data; });
        var minDate = dates[0];
        var maxDate = dates[dates.length - 1];

        container.innerHTML =
            '<div class="timeline-current" id="timeline-current-date">Estado atual</div>' +
            '<input type="range" class="timeline-slider" id="timeline-slider" min="0" max="' + dates.length + '" value="' + dates.length + '">' +
            '<div class="timeline-dates"><span>' + formatDateBR(minDate) + '</span><span>' + formatDateBR(maxDate) + '</span></div>';

        var slider = document.getElementById('timeline-slider');
        var label = document.getElementById('timeline-current-date');
        slider.addEventListener('input', function() {
            var idx = parseInt(slider.value);
            if (idx >= dates.length) {
                label.textContent = 'Estado atual';
                currentData = null;
                loadEstado(null);
            } else {
                var d = dates[idx];
                label.textContent = formatDateBR(d);
                currentData = d;
                loadEstado(d);
            }
        });
    }

    function formatDateBR(dateStr) {
        if (!dateStr || dateStr === 'None') return '-';
        var parts = dateStr.split('-');
        if (parts.length !== 3) return dateStr;
        return parts[2] + '/' + parts[1] + '/' + parts[0];
    }

    function renderRecordsTable() {
        var tbody = document.getElementById('odontogram-records-body');
        if (!tbody) return;
        var allRecords = [];
        for (var key in estadoAtual) {
            allRecords.push(estadoAtual[key]);
        }
        allRecords.sort(function(a, b) {
            if (a.dente !== b.dente) return a.dente - b.dente;
            return (a.face || '').localeCompare(b.face || '');
        });

        if (allRecords.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted py-3">Nenhum registro no odontograma</td></tr>';
            return;
        }

        var html = '';
        allRecords.forEach(function(reg) {
            var condInfo = CONDICOES[reg.condicao] || { cor: '#ccc', label: reg.condicao };
            html += '<tr>';
            html += '<td class="fw-bold">' + reg.dente + '</td>';
            html += '<td>' + (reg.face || '<em>Todos</em>') + '</td>';
            html += '<td><span class="badge-condicao" style="background:' + condInfo.cor + ';color:' + (reg.condicao === 'ausente' ? '#333' : '#fff') + '">' + condInfo.label + '</span></td>';
            html += '<td>' + (reg.observacoes || '-') + '</td>';
            html += '<td>' + (reg.data_registro || '-') + '</td>';
            html += '</tr>';
        });
        tbody.innerHTML = html;
    }

    function submitRegistro(form) {
        var formData = new FormData(form);
        var dente = formData.get('dente');
        var condicao = formData.get('condicao');
        if (!dente || !condicao) {
            alert('Selecione um dente e uma condição.');
            return;
        }
        return fetch('/api/odontograma/' + PRONTUARIO_ID, {
            method: 'POST',
            body: formData
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.ok) {
                var modal = bootstrap.Modal.getInstance(document.getElementById('modalOdontograma'));
                if (modal) modal.hide();
                form.reset();
                refresh();
            } else {
                alert('Erro ao salvar: ' + (data.detail || 'desconhecido'));
            }
        })
        .catch(function(err) {
            alert('Erro de rede: ' + err.message);
        });
    }

    function deleteRegistro(registroId) {
        if (!confirm('Remover este registro do odontograma?')) return;
        fetch('/api/odontograma/' + PRONTUARIO_ID + '/' + registroId, { method: 'DELETE' })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.ok) refresh();
                else alert('Erro ao remover.');
            });
    }

    function refresh() {
        loadEstado(currentData).then(function() {
            setupTooltips();
        });
        loadHistorico();
    }

    function init(prontuarioId, profissional) {
        PRONTUARIO_ID = prontuarioId;
        isProfissional = profissional;
        buildToothDefs();
        createSVG();

        var form = document.getElementById('form-odontograma');
        if (form) {
            form.addEventListener('submit', function(e) {
                e.preventDefault();
                submitRegistro(form);
            });
        }

        loadEstado(null).then(function() {
            setupTooltips();
        });
        loadHistorico();

        var modal = document.getElementById('modalOdontograma');
        if (modal) {
            modal.addEventListener('show.bs.modal', function() {
                if (selectedTooth) {
                    updateFaceModal(selectedTooth, selectedFace);
                }
            });
        }
    }

    return {
        init: init,
        refresh: refresh,
        deleteRegistro: deleteRegistro,
        CONDICOES: CONDICOES
    };
})();
