/* This board only embeds the demo routes; it never creates a network input client. */
(() => {
  const byId=id=>document.getElementById(id),themes=window.TouchHelmThemes;
  if(!themes)return;
  let selected=themes.state.id;
  const phone=byId('previewPhone'),desktop=byId('previewDesktop');
  const inputs=['Appearance','Motion','Contrast','Tab','State','Viewport','DesktopTab'].map(name=>byId(`preview${name}`));
  const preferences=()=>({appearance:byId('previewAppearance').value,motion:byId('previewMotion').value,contrast:byId('previewContrast').value});
  const label=value=>value.charAt(0).toUpperCase()+value.slice(1);
  const themeButtons=[];
  for(const theme of Object.values(themes.registry)){
    const button=document.createElement('button');button.type='button';button.dataset.themeId=theme.id;
    const dot=document.createElement('span');dot.className='preview-theme-dot';dot.setAttribute('aria-hidden','true');
    const name=document.createElement('span');name.textContent=theme.label;
    button.append(dot,name);button.addEventListener('click',()=>{selected=theme.id;update();});
    themeButtons.push(button);byId('previewThemes').appendChild(button);
  }
  function applyPhone(){
    const win=phone.contentWindow;
    if(!win?.TouchHelmThemes||!win.TouchHelmDemo)return false;
    win.TouchHelmThemes.apply(selected,preferences(),false);
    win.document.getElementById(`tab${byId('previewTab').value}`)?.click();
    win.TouchHelmDemo.setState(byId('previewState').value);
    return true;
  }
  function applyDesktop(){
    const win=desktop.contentWindow;
    if(!win?.TouchHelmThemes)return false;
    win.TouchHelmThemes.apply(selected,preferences(),false);
    const state=byId('previewState').value;
    if(win.TouchHelmDesktopPreview?.setState)win.TouchHelmDesktopPreview.setState(state);
    else win.dispatchEvent(new win.CustomEvent('touchhelm:preview-state',{detail:{state}}));
    const target=byId('previewDesktopTab').value;
    const buttons=[...win.document.querySelectorAll('.desktop-nav button')];
    buttons.find(button=>button.dataset.panel===target||button.dataset.view===target||button.getAttribute('aria-controls')===target||button.textContent.toLowerCase().trim()===target)?.click();
    return true;
  }
  function update(){
    themes.apply(selected,preferences(),false);
    for(const button of themeButtons)button.setAttribute('aria-pressed',String(button.dataset.themeId===selected));
    const [width,height]=byId('previewViewport').value.split(',').map(Number);
    phone.width=width;phone.height=height;phone.parentElement.style.setProperty('--preview-phone-width',`${width}px`);
    desktop.width=Math.max(820,Math.floor(desktop.parentElement.clientWidth));
    const state=label(byId('previewState').value),name=themes.registry[selected].label;
    byId('previewPhoneLabel').textContent=`${name} · ${byId('previewTab').value} · ${state} · Simulated`;
    byId('previewDesktopLabel').textContent=`${name} · ${label(byId('previewDesktopTab').value)} · ${state} · Simulated`;
    let phoneReady=false,desktopReady=false;
    try{phoneReady=applyPhone();desktopReady=applyDesktop();}catch(_){/* Same-origin fixture not loaded yet. */}
    byId('previewStatus').textContent=phoneReady&&desktopReady?'Both local fixture interfaces are ready.':'Waiting for the local demo interfaces. Preview commands remain simulated.';
  }
  inputs.forEach(input=>input.addEventListener('change',update));
  byId('previewState').addEventListener('change',()=>{const tabs={typing:'Trackpad',held:'Keyboard',menu:'Apps',notes:'Presenter',playing:'Media',paused:'Media','missing-artwork':'Media'};const target=tabs[byId('previewState').value];if(target){byId('previewTab').value=target;update();}});
  phone.addEventListener('load',update);desktop.addEventListener('load',update);update();
  window.addEventListener('resize',update);
})();
