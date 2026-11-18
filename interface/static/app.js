"use strict";

const $ = s => document.querySelector(s);
function esc(t){ return (t||"").replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

async function info(){
  try {
    const r = await fetch('/api/info'); const d = await r.json();
    $('#infoCorpus').textContent =
      `${d.n_documentos} projetos · vocabulário ${d.vocabulario} termos · `
      + `${d.postings} postings · granularidade "${d.granularidade}" · `
      + `stemming ${d.stemming?'on':'off'} · ${d.particoes} partições`;
  } catch(e){ $('#infoCorpus').textContent = 'índice não carregado'; }
}

async function detalhe(termo){
  const box = $('#detalhe');
  box.style.display = 'block';
  box.textContent = 'lendo postings de "'+termo+'" no índice…';
  const r = await fetch('/api/termo?t=' + encodeURIComponent(termo));
  const d = await r.json();
  let txt = '';
  for (const t of d.termos){
    if (!t.no_indice){ txt += `termo "${t.termo}": não está no índice\n`; continue; }
    txt += `termo "${t.termo}"  partição ${t.particao}  df=${t.df}  cf=${t.cf}\n`;
    txt += `campos: [${t.campos.join(', ')}]\n`;
    for (const p of t.postings){
      txt += `  unidade ${p.unidade}  tf=${JSON.stringify(p.tf)}  ${p.nome}  ${p.url}\n`;
    }
    txt += '\n';
  }
  box.textContent = txt.trim() || 'sem dados';
  box.scrollIntoView({behavior:'smooth', block:'nearest'});
}

async function buscar(q, k){
  $('#resultados').innerHTML = '<div class="vazio-res">buscando…</div>';
  $('#termos').innerHTML = ''; $('#meta').textContent = ''; $('#detalhe').style.display='none';
  const r = await fetch('/api/buscar?q=' + encodeURIComponent(q) + '&k=' + k);
  const d = await r.json();
  if (d.erro){ $('#resultados').innerHTML = '<div class="vazio-res">'+esc(d.erro)+'</div>'; return; }

  $('#meta').textContent = `${d.total} resultado(s) em ${d.ms} ms · termos analisados da consulta:`;
  $('#termos').innerHTML = d.lexico.map(l =>
    l.no_indice
      ? `<span class="chip" data-t="${esc(l.termo)}"><b>${esc(l.termo)}</b> · df ${l.df} · cf ${l.cf}</span>`
      : `<span class="chip vazio" title="não está no índice">${esc(l.termo)} · ausente</span>`
  ).join('');
  document.querySelectorAll('#termos .chip[data-t]').forEach(c =>
    c.onclick = () => detalhe(c.getAttribute('data-t')));

  if (!d.resultados.length){
    $('#resultados').innerHTML = '<div class="vazio-res">Nenhum projeto encontrado para essa consulta.</div>';
    return;
  }
  $('#resultados').innerHTML = d.resultados.map((x,i) => {
    const estrelas = (x.estrelas!==null && x.estrelas!==undefined && x.estrelas!=='') ? `⭐ ${esc(''+x.estrelas)}` : '';
    const linha2 = [
      `<span class="tag">${esc(x.site)}</span>`,
      x.linguagem ? `<span class="tag">${esc(x.linguagem)}</span>` : '',
      x.licenca ? `<span class="tag">${esc(x.licenca)}</span>` : '',
      estrelas
    ].filter(Boolean).join(' ');
    return `<div class="res">
      <span class="nota">${x.nota.toFixed(2)}</span>
      <div class="titulo">${i+1}. <a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.nome||x.url)}</a></div>
      <div class="linha2">${linha2}</div>
      <div class="trecho">${esc(x.trecho||'')}</div>
    </div>`;
  }).join('');
}

$('#form').addEventListener('submit', e => {
  e.preventDefault();
  const q = $('#q').value.trim(); if (!q) return;
  buscar(q, $('#k').value);
});
document.querySelectorAll('.exemplos a').forEach(a =>
  a.onclick = () => { $('#q').value = a.getAttribute('data-q'); buscar(a.getAttribute('data-q'), $('#k').value); });
info();

// Consulta pela URL (?q=...&k=...): permite compartilhar um link de busca.
const url0 = new URLSearchParams(location.search);
if (url0.get('q')) {
  $('#q').value = url0.get('q');
  if (url0.get('k')) $('#k').value = url0.get('k');
  buscar(url0.get('q'), $('#k').value);
}
