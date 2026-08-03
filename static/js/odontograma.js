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
            viewBox: '-27 -33 55 66',
            outline: 'M -4.5,24.6 C -6.3,24.5 -9.0,23.9 -9.0,23.9 C -9.0,23.9 -13.6,23.0 -15.5,21.9 C -17.6,20.7 -20.2,19.0 -20.6,17.4 C -21.0,15.8 -21.2,13.3 -21.0,11.5 L -20.9,11.4 C -20.6,9.2 -20.2,6.1 -19.8,2.6 C -19.6,0.9 -19.9,-0.0 -19.1,-2.5 C -18.3,-5.1 -17.9,-6.4 -17.4,-7.3 C -16.8,-8.3 -16.1,-9.1 -15.6,-10.1 C -14.9,-11.7 -13.5,-13.7 -12.3,-15.2 C -11.6,-16.1 -10.9,-16.9 -10.2,-17.5 C -9.4,-18.4 -7.8,-20.1 -6.9,-21.1 C -5.6,-22.6 -4.3,-23.9 -3.1,-24.3 C -2.1,-24.6 -0.8,-24.8 0.0,-25.0 C 1.2,-25.3 2.1,-25.6 3.9,-25.0 C 5.2,-24.6 6.2,-24.4 7.6,-22.9 C 9.4,-21.0 10.0,-19.9 10.6,-18.8 C 11.5,-17.2 12.7,-14.9 13.5,-13.4 C 14.0,-12.4 15.4,-10.7 16.9,-5.8 C 18.2,-1.8 18.9,0.7 19.2,1.8 C 19.5,3.0 20.0,4.8 20.3,7.0 C 20.6,10.6 21.1,13.4 21.1,16.4 C 21.0,19.0 21.1,20.7 20.1,21.8 C 19.3,22.6 18.4,23.4 17.3,23.9 C 15.6,24.5 14.1,25.0 12.8,25.2 C 11.6,25.4 6.8,25.4 3.2,25.1 C 1.9,25.0 0.2,25.0 -4.5,24.6 Z',
            shadow: 'M 8.0,-16.4 C 24.0,19.3 16.8,20.7 11.8,21.5 C 6.9,22.4 -12.2,19.2 -13.3,18.9 C -13.7,18.7 -20.9,18.8 -17.2,2.3 C -14.1,-11.3 -3.2,-20.1 -2.3,-20.7 C 0.3,-22.3 5.1,-22.8 8.0,-16.4 Z',
            highlight: 'M -15.8,13.5 C -15.5,13.8 -12.2,16.3 -8.3,18.2 C -5.6,19.4 -1.7,19.6 1.2,19.8 C 8.6,20.1 9.7,19.1 11.9,18.6 C 12.4,18.5 12.7,18.4 13.4,18.1',
            labels: [{x:0,y:31}]
        },
        canino: {
            viewBox: '-24 -33 47 66',
            outline: 'M -18.1,9.0 C -17.9,7.2 -17.5,-9.0 -7.3,-22.0 C -4.4,-25.7 6.0,-26.7 9.9,-23.7 C 16.9,-18.3 20.0,1.3 16.9,9.7 C 15.5,13.8 3.8,27.8 -1.9,25.2 C -7.4,22.7 -18.8,16.3 -18.1,9.0 Z',
            shadow: 'M 8.1,-19.6 C 13.8,-15.2 16.4,0.9 13.9,7.8 C 12.8,11.1 3.1,22.6 -1.5,20.4 C -5.4,18.7 -12.0,14.9 -13.9,10.8 C -18.2,1.5 -6.4,-31.0 8.1,-19.6 Z',
            highlight: 'M -12.1,8.1 C -11.6,8.6 -9.4,11.0 -7.1,12.8 C -3.5,15.5 -3.1,15.9 -1.4,16.9 C -0.1,17.6 2.7,18.6 11.3,8.6 M -6.0,-8.2 C -5.7,-8.4 -1.5,-6.5 3.5,-10.1',
            labels: [{x:0,y:31}]
        },
        premolar: {
            viewBox: '-22 -33 45 67',
            outline: 'M -7.4,-22.5 C -13.1,-18.4 -16.9,6.4 -17.0,6.5 C -17.0,7.9 -20.1,16.7 0.6,25.6 C 1.5,26.0 2.6,25.4 3.4,25.0 C 4.2,24.5 5.9,23.4 8.6,20.6 C 10.3,19.0 17.0,12.0 17.1,7.4 C 17.2,5.3 16.8,1.0 16.4,-3.1 C 16.0,-7.3 14.7,-14.8 13.8,-17.6 C 12.9,-20.4 8.1,-30.9 -7.4,-22.5 Z',
            shadow: 'M -6.3,-19.7 C -11.2,-16.2 -14.6,5.4 -14.6,5.6 C -14.6,6.8 -17.3,14.4 0.6,22.1 C 1.5,22.5 2.4,22.0 3.1,21.6 C 3.8,21.2 5.3,20.2 7.6,17.8 C 9.1,16.4 15.0,10.3 15.1,6.3 C 15.1,4.5 14.8,0.8 14.5,-2.8 C 14.1,-6.5 12.9,-13.0 12.1,-15.5 C 11.4,-17.8 7.2,-27.1 -6.3,-19.7 Z',
            highlight: 'M -11.7,12.4 C -11.5,12.5 -10.6,12.9 -5.6,15.0 C -2.8,16.2 -0.9,16.0 0.7,15.7 C 2.2,15.4 4.5,14.5 6.4,13.2 C 7.4,12.4 8.5,11.5 10.2,9.6 C 10.6,9.0 11.0,8.6 11.6,7.9 M -4.9,-14.5 C -2.5,-17.2 5.9,-16.8 5.9,-16.8',
            occlusalLine: 'M0,-22 C-8,-24 8,-24 0,-22',
            occlusalCross: ['M-6,-22 L6,-22', 'M0,-26 L0,-18'],
            labels: [{x:0,y:31}]
        },
        molar: {
            viewBox: '-30 -33 60 67',
            outline: 'M -15.3,18.3 C -13.6,19.7 1.6,34.4 17.8,17.5 C 18.9,16.4 28.3,1.1 18.7,-17.6 C 17.7,-19.7 17.0,-21.6 16.1,-22.6 C 14.7,-24.1 14.0,-24.8 12.3,-24.9 C 10.8,-25.0 9.3,-24.5 5.9,-23.7 C 4.2,-23.2 3.0,-23.0 -0.0,-24.2 C -1.1,-24.6 -2.7,-25.4 -4.8,-25.5 C -6.5,-25.6 -7.6,-25.5 -9.0,-24.6 C -11.1,-23.2 -12.7,-21.5 -13.9,-18.8 C -14.3,-18.1 -15.1,-16.7 -16.6,-13.7 C -17.6,-11.7 -18.8,-9.1 -19.8,-6.6 C -20.8,-4.1 -21.6,-2.0 -22.0,-0.4 C -22.6,1.9 -23.3,4.4 -22.8,6.7 L -22.8,6.7 C -22.4,8.1 -21.9,10.1 -20.5,12.2 C -19.1,14.4 -17.4,16.6 -15.3,18.3 Z',
            shadow: 'M -13.2,15.8 C -11.7,17.1 1.5,29.9 15.7,15.2 C 16.7,14.2 24.8,0.9 16.5,-15.5 C 15.6,-17.3 15.0,-19.0 14.2,-19.8 C 13.0,-21.1 12.3,-21.8 10.9,-21.9 C 9.6,-21.9 8.3,-21.5 5.3,-20.8 C 3.8,-20.4 2.8,-20.2 0.1,-21.2 C -0.8,-21.6 -2.2,-22.3 -4.0,-22.4 C -14.3,-22.9 -18.7,-1.8 -19.0,-0.5 L -19.0,-0.5 C -19.6,1.6 -21.5,8.7 -13.2,15.8 Z',
            highlight: 'M 9.5,-0.0 C 5.2,-0.9 -0.2,0.2 -1.4,2.9 C -0.9,-2.3 -6.2,-3.9 -10.3,-4.0 M 9.5,-0.0 C 12.4,0.4 14.8,1.8 15.2,4.3 M 9.5,-0.0 C 11.2,0.1 15.0,-0.0 16.3,-2.3 M -15.1,-2.9 C -14.7,-3.3 -12.9,-4.1 -10.3,-4.0 M -10.3,-4.0 C -11.8,-4.9 -14.6,-7.1 -14.1,-8.9',
            occlusalLine: 'M0,-22 C-8,-24 8,-24 0,-22',
            occlusalCross: ['M-6,-22 L6,-22', 'M0,-26 L0,-18'],
            labels: [{x:0,y:31}]
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

        var gradTooth = svgEl('linearGradient', { id: 'toothGradient', x1: '0', y1: '0', x2: '1', y2: '1' });
        var t1 = svgEl('stop', { offset: '0%', 'stop-color': '#f5f0ea' });
        var t2 = svgEl('stop', { offset: '50%', 'stop-color': '#e8e0d8' });
        var t3 = svgEl('stop', { offset: '100%', 'stop-color': '#d5cdc5' });
        gradTooth.appendChild(t1);
        gradTooth.appendChild(t2);
        gradTooth.appendChild(t3);
        defs.appendChild(gradTooth);

        var gradShadow = svgEl('linearGradient', { id: 'gradShadow', x1: '0', y1: '0', x2: '0.8', y2: '0.8' });
        var s1 = svgEl('stop', { offset: '0%', 'stop-color': '#000', 'stop-opacity': '0' });
        var s2 = svgEl('stop', { offset: '100%', 'stop-color': '#000', 'stop-opacity': '0.2' });
        gradShadow.appendChild(s1);
        gradShadow.appendChild(s2);
        defs.appendChild(gradShadow);

        var gradHi = svgEl('linearGradient', { id: 'gradHighlight', x1: '0', y1: '0', x2: '0.3', y2: '1' });
        var h1 = svgEl('stop', { offset: '0%', 'stop-color': '#fff', 'stop-opacity': '0.6' });
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
                transform: 'translate(' + startX + ',' + startY + ')' + (mirror ? ' scale(-1,1)' : '')
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
                    'M-12,-17 L12,-17 L13,-4 L-13,-4 Z',
                    'M-13,-4 L13,-4 L12,8 L-12,8 Z',
                    'M-12,8 L12,8 L8,19 L-8,19 Z',
                    'M-20,-21 L-12,-21 L-10,22 L-18,22 Z',
                    'M12,-21 L20,-21 L18,22 L10,22 Z'
                ];
            case 'canino':
                return [
                    'M-12,-18 L12,-18 L13,-4 L-13,-4 Z',
                    'M-13,-4 L13,-4 L11,10 L-11,10 Z',
                    'M-11,10 L11,10 L7,20 L-7,20 Z',
                    'M-17,-22 L-12,-22 L-10,24 L-16,24 Z',
                    'M12,-22 L17,-22 L16,24 L10,24 Z'
                ];
            case 'premolar':
                return [
                    'M-12,-18 L12,-18 L13,-2 L-13,-2 Z',
                    'M-13,-2 L13,-2 L11,10 L-11,10 Z',
                    'M-11,10 L11,10 L7,21 L-7,21 Z',
                    'M-16,-22 L-12,-22 L-10,25 L-15,25 Z',
                    'M12,-22 L16,-22 L15,25 L10,25 Z',
                    'M-12,-22 L12,-22 L8,-16 L-8,-16 Z'
                ];
            case 'molar':
                return [
                    'M-14,-18 L14,-18 L15,0 L-15,0 Z',
                    'M-15,0 L15,0 L13,12 L-13,12 Z',
                    'M-13,12 L13,12 L8,27 L-8,27 Z',
                    'M-20,-24 L-14,-24 L-12,33 L-18,33 Z',
                    'M14,-24 L20,-24 L18,33 L12,33 Z',
                    'M-14,-24 L14,-24 L10,-16 L-10,-16 Z'
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
