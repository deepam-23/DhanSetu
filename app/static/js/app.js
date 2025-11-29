async function postJSON(url, data){
  const res = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data), credentials:'include'});
  const text = await res.text();
  try{ return {ok:res.ok, status:res.status, data: JSON.parse(text)} }catch{ return {ok:res.ok, status:res.status, data:text} }
}
function byId(id){return document.getElementById(id)}

function serializeForm(form){
  const o = {};
  new FormData(form).forEach((v,k)=>{o[k]=v});
  return o;
}

function show(el, html, isError=false){
  el.hidden = false;
  el.className = 'result' + (isError ? ' alert error' : ' alert success');
  el.innerHTML = html;
}

document.addEventListener('DOMContentLoaded', ()=>{
  // Loan form handlers
  const loanForm = document.getElementById('loan-form');
  const loanResult = document.getElementById('loan-result');
  const eligBtn = document.getElementById('eligibility-btn');
  if(loanForm){
    loanForm.addEventListener('submit', async (e)=>{
      e.preventDefault();
      const data = serializeForm(loanForm);
      const payload = { data };
      const r = await postJSON((window.LoanUI||{}).endpoint || '/api/loan/save-draft', payload);
      if(r.ok){
        show(loanResult, `Draft saved. Application ID: <b>${r.data.id}</b>`);
      }else{
        show(loanResult, `Error (${r.status}): ${typeof r.data==='string'? r.data : (r.data.error||'Unknown')}`, true);
      }
    });

    if(eligBtn){
      eligBtn.addEventListener('click', ()=>{
        const d = serializeForm(loanForm);
        const amount = Number(d.amount||0);
        const term = Number(d.term||0);
        const income = Number(d.income||0);
        const emi = Number(d.emi||0);
        const credit = Number(d.credit_score||0);
        const age = Number(d.age||0);
        const emp = (d.employment_type||'').toLowerCase();
        const res = (d.residence_type||'').toLowerCase();

        // Simple EMI calc with flat interest approximation
        const annualRate = 0.14; // 14% APR example
        const r = annualRate/12;
        const emiNeeded = term>0 ? Math.round((amount*r*Math.pow(1+r,term))/(Math.pow(1+r,term)-1)) : 0;

        // Capacity with stability modifiers
        let capacity = Math.max(0, income - emi);
        let boost = 0;
        
        // Age-based eligibility factors
        if (age < 21) {
          boost -= 0.10;  // Penalty for very young applicants
        } else if (age < 25) {
          boost -= 0.05;  // Small penalty for young adults
        } else if (age >= 21 && age <= 60) {
          if (age >= 25 && age <= 45) {
            boost += 0.08;  // Prime age bracket
          } else if (age > 45 && age <= 55) {
            boost += 0.05;  // Good age bracket
          } else if (age > 55 && age <= 60) {
            boost += 0.02;  // Acceptable age bracket
          }
        } else {
          boost -= 0.15;  // Penalty for applicants over 60 (retirement risk)
        }
        
        // Credit score factors
        if(credit >= 800) boost += 0.12; else if(credit >= 750) boost += 0.08; else if(credit >= 700) boost += 0.04;
        
        // Employment factors
        if(emp === 'salaried') boost += 0.05; 
        else if(emp === 'self_employed') boost += 0.02;
        else if(emp === 'student') boost -= 0.10;
        else if(emp === 'retired') boost -= 0.05;
        
        // Residence factors
        if(res === 'owned') boost += 0.03; else if(res === 'parental') boost += 0.01;
        
        const boostedCapacity = Math.round(capacity * (1 + boost));

        const eligible = boostedCapacity >= emiNeeded && amount>0 && term>0 && age >= 21 && age <= 60;
        const reasons = [];
        if(age) reasons.push(`Age: <b>${age}</b> (${age < 21 || age > 60 ? 'Not eligible' : 'Eligible range'})`);
        if(credit) reasons.push(`Credit score adj: <b>${Math.round(boost*100)}%</b> total boost`);
        if(emp) reasons.push(`Employment: <b>${emp}</b>`);
        if(res) reasons.push(`Residence: <b>${res}</b>`);

        let msg = `Required EMI: <b>₹${emiNeeded.toLocaleString()}</b><br/>`+
                    `Capacity (base): <b>₹${capacity.toLocaleString()}</b><br/>`+
                    `Capacity (adjusted): <b>₹${boostedCapacity.toLocaleString()}</b>`+
                    (reasons.length? `<br/>${reasons.join(' • ')}` : '')+
                    `<br/>Eligibility: <b>${eligible? 'Eligible' : 'Not Eligible'}</b>`;
        if(eligible){
          msg += `<div class="kyc-cta"><a class="btn" href="/kyc">Proceed to KYC</a></div>`;
        }
        show(loanResult, msg, !eligible);
      });
    }
  }

  // KYC form handlers
  const kycStartBtn = document.getElementById('kyc-start');
  const kycForm = document.getElementById('kyc-form');
  const kycResult = document.getElementById('kyc-result');
  if(kycStartBtn){
    kycStartBtn.addEventListener('click', async ()=>{
      const r = await postJSON((window.KYCUI||{}).start || '/api/kyc/start', {});
      if(r.ok){
        show(kycResult, `KYC started. Status: <b>${r.data.status}</b>`);
      }else{
        show(kycResult, `Error (${r.status}): ${r.data.error||'Unknown'}`, true);
      }
    });
  }
  if(kycForm){
    kycForm.addEventListener('submit', async (e)=>{
      e.preventDefault();
      const data = serializeForm(kycForm);
      const r = await postJSON((window.KYCUI||{}).finalize || '/api/kyc/finalize', data);
      if(r.ok){
        const pdfUrl = (window.KYCUI||{}).myPdf || '/api/kyc/me/pdf';
        show(kycResult, `KYC finalized. ID: <b>${r.data.kyc_id}</b><br/><a href="${pdfUrl}" target="_blank">Download PDF</a>`);
      }else{
        show(kycResult, `Error (${r.status}): ${r.data.error||'Unknown'}`, true);
      }
    });
  }

  // Banker lookup handlers
  const bankerForm = document.getElementById('banker-form');
  const bankerResult = document.getElementById('banker-result');
  if(bankerForm){
    bankerForm.addEventListener('submit', async (e)=>{
      e.preventDefault();
      const { kyc_id } = serializeForm(bankerForm);
      if(!kyc_id) return;
      const url = ((window.BankerUI||{}).lookup || '/api/banker/kyc/') + encodeURIComponent(kyc_id);
      try{
        const res = await fetch(url, {credentials:'include'});
        const text = await res.text();
        const data = (()=>{try{return JSON.parse(text)}catch{return text}})();
        if(res.ok){
          const pdfLink = `/api/banker/kyc/${encodeURIComponent(kyc_id)}/pdf`;
          show(bankerResult, `KYC: <b>${data.kyc_id}</b><br/>Name: ${data.name}<br/>DOB: ${data.dob}<br/>Status: ${data.status}<br/>Checksum: ${data.pdf_checksum}<br/>Signature: ${data.verification_signature}<br/><a href="${pdfLink}" target="_blank">Download PDF</a>`);
        }else{
          show(bankerResult, `Error (${res.status}): ${data.error||'Unknown'}`, true);
        }
      }catch(err){
        show(bankerResult, `Network error: ${err}`, true);
      }
    });
  }

  // Chatbot handlers
  const chatRoot = document.getElementById('chatbot');
  const chatToggle = document.getElementById('chatbot-toggle');
  const chatPanel = document.getElementById('chatbot-panel');
  const chatClose = document.getElementById('chatbot-close');
  const chatForm = document.getElementById('chatbot-form');
  const chatInput = document.getElementById('chatbot-text');
  const chatMessages = document.getElementById('chatbot-messages');

  function addMsg(text, who='bot'){
    if(!chatMessages) return;
    const div = document.createElement('div');
    div.className = 'msg ' + (who==='me' ? 'me' : 'bot');
    div.textContent = text;
    chatMessages.appendChild(div);
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }
  // Dedicated chat page: auto-greet once
  if(chatMessages && chatMessages.dataset && chatMessages.dataset.init === 'greet'){
    addMsg('Hello! Ask me about loans, KYC, eligibility, documents, or interest rates.');
  }

  function openChat(){
    if(!chatPanel || !chatToggle) return;
    chatPanel.hidden = false;
    chatToggle.setAttribute('aria-expanded','true');
    if(chatMessages && chatMessages.children.length===0){
      addMsg('Hello! Ask me about loans, KYC, eligibility, documents, or interest rates.');
    }
    if(chatInput) chatInput.focus();
  }

  // Respect prior close within this tab session
  if(chatRoot && sessionStorage.getItem('chatbotClosed') === '1'){
    chatRoot.style.display = 'none';
  }

  if(chatToggle && chatPanel){
    chatToggle.addEventListener('click', ()=>{
      const open = chatPanel.hidden === false;
      chatPanel.hidden = open;
      chatToggle.setAttribute('aria-expanded', String(!open));
      if(!open){
        if(chatMessages && chatMessages.children.length===0){
          addMsg('Hello! Ask me about loans, KYC, eligibility, documents, or interest rates.');
        }
        if(chatInput) chatInput.focus();
      }
    });
  }
  // Note: navbar now links to /chat, so no interception required.
  document.querySelectorAll('.open-chat').forEach(el=>{
    el.addEventListener('click', (e)=>{ e.preventDefault(); openChat(); });
  });
  if(chatClose){
    chatClose.addEventListener('click', ()=>{
      if(chatRoot){
        chatRoot.style.display = 'none';
        try{ sessionStorage.setItem('chatbotClosed','1'); }catch{}
      }else if(chatPanel && chatToggle){
        chatPanel.hidden = true;
        chatToggle.setAttribute('aria-expanded','false');
      }
    });
  }
  // Delegated clicks as a fallback to ensure reliability
  document.addEventListener('click', (e)=>{
    const t = e.target;
    if(!t) return;
    // Open triggers
    if(t.matches('.open-chat') || (t.closest && t.closest('.open-chat'))){
      e.preventDefault();
      openChat();
      return;
    }
    if(t.matches('#chatbot-toggle')){
      // handled above; if not bound, handle here
      e.preventDefault();
      if(chatPanel && chatToggle){
        const open = chatPanel.hidden === false;
        chatPanel.hidden = open;
        chatToggle.setAttribute('aria-expanded', String(!open));
        if(!open){
          if(chatMessages && chatMessages.children.length===0){
            addMsg('Hello! Ask me about loans, KYC, eligibility, documents, or interest rates.');
          }
          if(chatInput) chatInput.focus();
        }
      }
      return;
    }
    if(t.matches('#chatbot-close')){
      e.preventDefault();
      if(chatRoot){
        chatRoot.style.display = 'none';
        try{ sessionStorage.setItem('chatbotClosed','1'); }catch{}
      }else if(chatPanel && chatToggle){
        chatPanel.hidden = true;
        chatToggle.setAttribute('aria-expanded','false');
      }
      return;
    }
  });
  if(chatForm && chatInput){
    chatForm.addEventListener('submit', async (e)=>{
      e.preventDefault();
      const message = (chatInput.value||'').trim();
      if(!message) return;
      addMsg(message, 'me');
      chatInput.value='';
      try{
        const r = await postJSON('/api/chat', {message});
        if(r.ok && r.data && r.data.reply){
          addMsg(r.data.reply, 'bot');
        }else{
          addMsg('Sorry, something went wrong.', 'bot');
        }
      }catch(err){
        addMsg('Network error. Please try again.', 'bot');
      }
    });
  }
});
