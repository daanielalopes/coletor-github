"use strict";

const $ = s => document.querySelector(s);
const $$ = s => Array.from(document.querySelectorAll(s));
function esc(t){ return (t || "").replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

// Guarda os resultados da última busca para filtrar/ordenar sem nova requisição.
let ULTIMA = null;

// ---------------------------------------------------------------------------
// Tema (claro/escuro), persistido no localStorage
// ---------------------------------------------------------------------------
function aplicarTema(tema){
  document.documentElement.setAttribute("data-tema", tema);
  try { localStorage.setItem("tema", tema); } catch (e) {}
}
(function iniciarTema(){
  let tema = "claro";
  try { tema = localStorage.getItem("tema"); } catch (e) {}
  if (!tema) {
    tema = (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches)
      ? "escuro" : "claro";
  }
  aplicarTema(tema);
})();
$("#btnTema").addEventListener("click", () => {
  const atual = document.documentElement.getAttribute("data-tema");
  aplicarTema(atual === "escuro" ? "claro" : "escuro");
});

// ---------------------------------------------------------------------------
// Info do corpus (cabeçalho)
// ---------------------------------------------------------------------------
async function info(){
  try {
    const r = await fetch("/api/info");
    const d = await r.json();
    $("#infoCorpus").textContent =
      `${d.n_documentos} projetos · vocabulário ${d.vocabulario} termos · `
      + `${d.postings} postings · granularidade "${d.granularidade}" · `
      + `stemming ${d.stemming ? "on" : "off"} · ${d.particoes} partições`;
  } catch (e) {
    $("#infoCorpus").textContent = "índice não carregado";
  }
}

// ---------------------------------------------------------------------------
// Detalhe de um termo (postings lidas do índice)
// ---------------------------------------------------------------------------
async function detalhe(termo){
  const box = $("#detalhe");
  box.hidden = false;
  box.textContent = `lendo postings de "${termo}" no índice…`;
  const r = await fetch("/api/termo?t=" + encodeURIComponent(termo));
  const d = await r.json();
  let txt = "";
  for (const t of d.termos){
    if (!t.no_indice){ txt += `termo "${t.termo}": não está no índice\n`; continue; }
    txt += `termo "${t.termo}"  partição ${t.particao}  df=${t.df}  cf=${t.cf}\n`;
    txt += `campos: [${t.campos.join(", ")}]\n`;
    for (const p of t.postings){
      txt += `  unidade ${p.unidade}  tf=${JSON.stringify(p.tf)}  ${p.nome}  ${p.url}\n`;
    }
    txt += "\n";
  }
  box.textContent = txt.trim() || "sem dados";
  box.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// ---------------------------------------------------------------------------
// Filtros e ordenação (client-side, sobre a última busca)
// ---------------------------------------------------------------------------
function opcoesUnicas(resultados, campo){
  const vals = new Set();
  for (const r of resultados){
    const v = (r[campo] || "").toString().trim();
    if (v) vals.add(v);
  }
  return Array.from(vals).sort((a, b) => a.localeCompare(b, "pt-br", { sensitivity: "base" }));
}

function preencherSelect(sel, valores){
  const atual = sel.value;
  const primeira = sel.querySelector("option"); // "Todos/Todas"
  sel.innerHTML = "";
  sel.appendChild(primeira);
  for (const v of valores){
    const o = document.createElement("option");
    o.value = v; o.textContent = v;
    sel.appendChild(o);
  }
  // mantém a seleção se o valor ainda existir
  sel.value = valores.includes(atual) ? atual : "";
}

function montarFiltros(resultados){
  $$("#filtros select[data-campo]").forEach(sel => {
    preencherSelect(sel, opcoesUnicas(resultados, sel.dataset.campo));
  });
}

function aplicarFiltrosOrdenacao(){
  if (!ULTIMA) return;
  let itens = ULTIMA.resultados.slice();

  // filtros
  $$("#filtros select[data-campo]").forEach(sel => {
    const v = sel.value;
    if (v){ itens = itens.filter(r => (r[sel.dataset.campo] || "") === v); }
  });

  // ordenação
  const ord = $("#ordenar").value;
  if (ord === "estrelas"){
    itens.sort((a, b) => (Number(b.estrelas) || 0) - (Number(a.estrelas) || 0));
  } else if (ord === "nome"){
    itens.sort((a, b) => (a.nome || "").localeCompare(b.nome || "", "pt-br", { sensitivity: "base" }));
  } // "relevancia" = ordem original (já vem do Buscador)

  renderResultados(itens, ULTIMA.resultados.length);
}

function renderResultados(itens, totalBruto){
  const cont = $("#resultados");
  if (!itens.length){
    cont.innerHTML = '<div class="vazio-res">Nenhum projeto corresponde aos filtros selecionados.</div>';
    return;
  }
  cont.innerHTML = itens.map((x, i) => {
    const estrelas = (x.estrelas !== null && x.estrelas !== undefined && x.estrelas !== "")
      ? `<span class="tag estrelas">⭐ ${esc("" + x.estrelas)}</span>` : "";
    const linha2 = [
      `<span class="tag">${esc(x.site)}</span>`,
      x.linguagem ? `<span class="tag">${esc(x.linguagem)}</span>` : "",
      x.licenca ? `<span class="tag">${esc(x.licenca)}</span>` : "",
      estrelas
    ].filter(Boolean).join(" ");
    return `<article class="res">
      <div class="titulo"><span class="num">${i + 1}.</span>
        <a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.nome || x.url)}</a></div>
      <span class="nota" title="pontuação BM25/BM25F">${x.nota.toFixed(2)}</span>
      <div class="linha2">${linha2}</div>
      <div class="trecho">${esc(x.trecho || "")}</div>
    </article>`;
  }).join("");

  const filtrados = totalBruto - itens.length;
  $("#meta").innerHTML =
    `<strong>${itens.length}</strong> de <strong>${totalBruto}</strong> resultado(s)`
    + ` em ${ULTIMA.ms} ms`
    + (filtrados > 0 ? ` · ${filtrados} ocultos por filtro` : "")
    + ` · termos analisados:`;
}

// ---------------------------------------------------------------------------
// Busca
// ---------------------------------------------------------------------------
async function buscar(q, k){
  $("#inicio").hidden = true;
  $("#painel").hidden = true;
  $("#resultados").innerHTML = '<div class="carregando"><div class="spinner"></div>buscando…</div>';

  let d;
  try {
    const r = await fetch("/api/buscar?q=" + encodeURIComponent(q) + "&k=" + k);
    d = await r.json();
  } catch (e) {
    $("#resultados").innerHTML = '<div class="vazio-res">Falha ao consultar o servidor.</div>';
    return;
  }
  if (d.erro){
    $("#resultados").innerHTML = '<div class="vazio-res">' + esc(d.erro) + "</div>";
    return;
  }

  ULTIMA = d;
  $("#painel").hidden = false;
  $("#detalhe").hidden = true;

  // chips dos termos analisados
  $("#termos").innerHTML = d.lexico.map(l =>
    l.no_indice
      ? `<button class="chip" data-t="${esc(l.termo)}" title="ver postings no índice"><b>${esc(l.termo)}</b> · df ${l.df} · cf ${l.cf}</button>`
      : `<span class="chip vazio" title="não está no índice">${esc(l.termo)} · ausente</span>`
  ).join("");
  $$("#termos .chip[data-t]").forEach(c =>
    c.addEventListener("click", () => detalhe(c.dataset.t)));

  if (!d.resultados.length){
    $("#filtros").style.display = "none";
    $("#meta").innerHTML = `<strong>0</strong> resultado(s) em ${d.ms} ms · termos analisados:`;
    $("#resultados").innerHTML =
      '<div class="vazio-res">Nenhum projeto encontrado para essa consulta.</div>';
    return;
  }

  $("#filtros").style.display = "";
  montarFiltros(d.resultados);
  aplicarFiltrosOrdenacao();
}

// ---------------------------------------------------------------------------
// Eventos
// ---------------------------------------------------------------------------
$("#form").addEventListener("submit", e => {
  e.preventDefault();
  const q = $("#q").value.trim();
  if (!q) return;
  buscar(q, $("#k").value);
});

$$("#exemplos button").forEach(b =>
  b.addEventListener("click", () => {
    $("#q").value = b.dataset.q;
    buscar(b.dataset.q, $("#k").value);
  }));

$("#ordenar").addEventListener("change", aplicarFiltrosOrdenacao);
$$("#filtros select[data-campo]").forEach(sel =>
  sel.addEventListener("change", aplicarFiltrosOrdenacao));
$("#limparFiltros").addEventListener("click", () => {
  $$("#filtros select[data-campo]").forEach(sel => { sel.value = ""; });
  $("#ordenar").value = "relevancia";
  aplicarFiltrosOrdenacao();
});

info();

// Consulta pela URL (?q=...&k=...): permite compartilhar um link de busca.
const url0 = new URLSearchParams(location.search);
if (url0.get("q")){
  $("#q").value = url0.get("q");
  if (url0.get("k")) $("#k").value = url0.get("k");
  buscar(url0.get("q"), $("#k").value);
}
