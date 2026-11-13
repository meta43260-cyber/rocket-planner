const $=id=>document.getElementById(id);
let token=sessionStorage.getItem("rp_admin_token")||"",catalogData=null;
function status(x){$("status").textContent=typeof x==="string"?x:JSON.stringify(x,null,2)}
window.addEventListener("error",event=>{const el=$("status");if(el)el.textContent="JavaScript error: "+(event.message||"unknown error")});
window.addEventListener("unhandledrejection",event=>{const el=$("status");if(el)el.textContent="Request error: "+(event.reason?.message||String(event.reason||"unknown error"))});
async function api(path,method="GET",body){
 const headers={};if(token)headers.Authorization="Bearer "+token;
 if(body!==undefined)headers["Content-Type"]="application/json";
 const r=await fetch("/api"+path,{method,headers,body:body===undefined?undefined:JSON.stringify(body)});
 const d=await r.json().catch(()=>({}));if(!r.ok)throw Error(d.detail||"Request failed: "+r.status);return d
}
function esc(v){return String(v??"—").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
function n(v,unit=""){return v===null||v===undefined?"—":Number(v).toLocaleString("en-US")+unit}
function renderCatalog(data){
 catalogData=data;
 const root=$("catalog");const rockets=data.rockets||[],versions=data.versions||[];
 if(!rockets.length){root.innerHTML='<p class="empty">ยังไม่มีข้อมูลจรวด</p>';return}
 root.innerHTML=rockets.map(r=>{
  const vs=versions.filter(v=>v.rocket_id===r.id);
  return '<article class="rocket-entry"><div class="rocket-head"><div><h3>'+esc(r.name)+'</h3><p>'+esc(r.manufacturer)+' · '+esc(r.country)+' · '+esc(r.vehicle_type)+'</p><code>'+esc(r.slug)+'</code></div><span class="pill">'+vs.length+' revision</span></div>'+
   (vs.length?vs.map(v=>{
    const stages=(data.stages||[]).filter(x=>x.version_id===v.id);
    const boosters=(data.boosters||[]).filter(x=>x.version_id===v.id);
    const sources=(data.sources||[]).filter(x=>x.version_id===v.id);
    const conf=v.confidence||"—";
    return '<section class="version-entry"><div class="version-head"><strong>Revision '+esc(v.revision)+'</strong><span class="pill draft">'+esc(v.status)+' · '+esc(conf)+'</span></div>'+
     '<div class="metric-grid"><div><small>LEO capacity</small><b>'+n(v.payload_capacity_leo_kg,' kg')+'</b></div><div><small>Fairing mass</small><b>'+n(v.fairing_mass_kg,' kg')+'</b></div></div>'+
     '<p class="note">'+esc(v.notes||"ไม่มีหมายเหตุ")+'</p>'+
     '<h4>Stages ('+stages.length+')</h4>'+(stages.length?'<div class="table-wrap"><table><thead><tr><th>Stage</th><th>Thrust SL/Vac (kN)</th><th>ISP SL/Vac (s)</th><th>Propellant (kg)</th><th>Dry (kg)</th><th>Burn (s)</th></tr></thead><tbody>'+stages.map(s=>'<tr><td>'+esc(s.stage_number)+'. '+esc(s.name)+'</td><td>'+n(s.thrust_sl_kn)+' / '+n(s.thrust_vac_kn)+'</td><td>'+n(s.isp_sl_s)+' / '+n(s.isp_vac_s)+'</td><td>'+n(s.prop_mass_kg)+'</td><td>'+n(s.dry_mass_kg)+'</td><td>'+n(s.burn_time_s)+'</td></tr>').join("")+'</tbody></table></div>':'<p class="muted">ไม่มีข้อมูล Stage</p>')+
     '<h4>Boosters ('+boosters.length+')</h4>'+(boosters.length?'<div class="table-wrap"><table><thead><tr><th>ชื่อ</th><th>จำนวน</th><th>Thrust SL/Vac (kN)</th><th>Propellant (kg)</th><th>Burn (s)</th><th>Ignition (s)</th></tr></thead><tbody>'+boosters.map(b=>'<tr><td>'+esc(b.name)+'</td><td>'+n(b.quantity)+'</td><td>'+n(b.thrust_sl_kn)+' / '+n(b.thrust_vac_kn)+'</td><td>'+n(b.prop_mass_kg)+'</td><td>'+n(b.burn_time_s)+'</td><td>'+n(b.ignite_t_s)+'</td></tr>').join("")+'</tbody></table></div>':'<p class="muted">ไม่มี Booster</p>')+
     '<h4>Sources ('+sources.length+')</h4>'+(sources.length?'<ul class="source-list">'+sources.map(s=>'<li><strong>'+esc(s.title)+'</strong> · '+esc(s.publisher)+' · '+esc(s.confidence)+'<br><small>'+esc(s.source_type)+' · '+(s.source_url?'<a href="'+esc(s.source_url)+'" target="_blank" rel="noopener">เปิดแหล่งข้อมูล</a>':"ไม่มี URL")+'</small><p>'+esc(s.notes)+'</p></li>').join("")+'</ul>':'<p class="muted">ไม่มีแหล่งอ้างอิง</p>')+
     '<div class="version-actions"><button type="button" data-rocket="'+esc(r.id)+'" data-version="'+esc(v.id)+'">เลือก Revision นี้เพื่อจัดการ</button><span>สถานะ: '+esc(v.status)+(v.is_current?' · Current':'')+'</span></div></section>'
   }).join(""):'<p class="muted">ยังไม่มี Revision</p>')+'</article>'
 }).join("");
 refreshDbSelects();
 root.querySelectorAll("[data-version]").forEach(btn=>btn.addEventListener("click",()=>{
  const rocketId=btn.dataset.rocket,versionId=btn.dataset.version;
  $("db-rocket-select").value=rocketId;$("db-rocket-select").dispatchEvent(new Event("change"));
  $("db-version-rocket").value=rocketId;fillDbVersionSelect();
  const version=(catalogData?.versions||[]).find(v=>v.id===versionId);
  if(version?.status==="draft"){
   $("db-version-select").value=versionId;fillDbVersionForm();
   $("db-child-version").value=versionId;fillDbChildSelect();
  }
  $("quick-db-editor").scrollIntoView({behavior:"smooth",block:"start"});
  status(version?.status==="draft"?"เลือก Draft เพื่อแก้ไขแล้ว":"Revision ที่เผยแพร่แล้วอ่านได้อย่างเดียว · สร้าง Draft ใหม่เพื่อแก้ไข");
 }));
}
async function load(){
 const me=await api("/admin/me");$("who").textContent=me.user.email+" · ADMIN";
 const data=await api("/admin/rockets");renderCatalog(data);
 status("เชื่อมต่อฐานข้อมูลแล้ว · "+(data.rockets||[]).length+" rockets / "+(data.versions||[]).length+" revisions")
}
function show(){$("login-panel").classList.toggle("hidden",!!token);$("workspace").classList.toggle("hidden",!token)}
$("login").onclick=async()=>{try{const r=await fetch("/api/admin/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({email:$("email").value,password:$("password").value})});const d=await r.json();if(!r.ok)throw Error(d.detail||"Login failed");token=d.access_token;sessionStorage.setItem("rp_admin_token",token);$("password").value="";show();await load()}catch(e){alert(e.message)}};
$("logout").onclick=()=>{token="";sessionStorage.removeItem("rp_admin_token");show()};
$("refresh").onclick=()=>load().catch(e=>status(e.message));
const dbFields={
 rocket_stages:[["stage_number","ลำดับ Stage","number"],["name","ชื่อ Stage","text"],["thrust_sl_kn","Thrust sea level (kN) · ไม่บังคับ","number"],["thrust_vac_kn","Thrust vacuum (kN)","number"],["isp_sl_s","ISP sea level (s) · ไม่บังคับ","number"],["isp_vac_s","ISP vacuum (s)","number"],["prop_mass_kg","Propellant (kg)","number"],["dry_mass_kg","Dry mass (kg)","number"],["burn_time_s","Burn time (s)","number"],["reference_area_m2","Reference area (m²)","number"],["ignition_delay_s","Ignition delay (s)","number"],["thrust_curve_json","Thrust-Time Curve JSON · [[วินาที,kN],...]","json"]],
 rocket_boosters:[["name","ชื่อ Booster","text"],["quantity","จำนวน","number"],["thrust_sl_kn","Thrust sea level (kN) · ไม่บังคับ","number"],["thrust_vac_kn","Thrust vacuum (kN)","number"],["isp_sl_s","ISP sea level (s) · ไม่บังคับ","number"],["isp_vac_s","ISP vacuum (s)","number"],["prop_mass_kg","Propellant (kg)","number"],["dry_mass_kg","Dry mass (kg)","number"],["burn_time_s","Burn time (s)","number"],["reference_area_m2","Reference area (m²)","number"],["ignite_t_s","Ignition time (s)","number"],["jettison_delay_s","Jettison delay (s)","number"],["thrust_curve_json","Thrust-Time Curve JSON · [[วินาที,kN],...]","json"]],
 rocket_sources:[["title","ชื่อแหล่งข้อมูล","text"],["publisher","Publisher","text"],["source_type","ประเภทแหล่งข้อมูล","text"],["source_url","URL","url"],["confidence","ความเชื่อมั่น (A-D)","text"],["accessed_at","วันที่เข้าถึง","date"],["notes","หมายเหตุ","text"]]
};
function dbVal(id){return $(id).value.trim()}
function dbNum(id){const v=dbVal(id);return v===""?null:Number(v)}
function curvePointsFromEditor(box){
 const points=[...box.querySelectorAll("[data-curve-row]")].map(tr=>[
  Number(tr.querySelector("[data-curve-time]").value),
  Number(tr.querySelector("[data-curve-thrust]").value)
 ]);
 return points;
}
function curveRefresh(box){
 const points=curvePointsFromEditor(box),hidden=box.querySelector("[data-db-field=thrust_curve_json]");
 hidden.value=points.every(p=>Number.isFinite(p[0])&&Number.isFinite(p[1])&&p[0]>=0&&p[1]>0)?JSON.stringify(points):"";
 const svg=box.querySelector("[data-curve-chart]"),w=520,h=170,pad=30;
 if(!points.length){svg.innerHTML='<text x="260" y="85" text-anchor="middle" fill="#9eb1c4" font-size="13">เพิ่มจุดข้อมูลเพื่อแสดงกราฟ</text>';return}
 const maxT=Math.max(1,...points.map(p=>p[0])),maxF=Math.max(1,...points.map(p=>p[1]));
 const xy=points.map(([t,f])=>[pad+t/maxT*(w-pad*2),h-pad-f/maxF*(h-pad*2)]);
 const path=xy.map((p,i)=>(i?"L":"M")+p[0].toFixed(1)+" "+p[1].toFixed(1)).join(" ");
 svg.innerHTML='<path d="M'+pad+' '+(h-pad)+' H'+(w-pad)+' M'+pad+' '+pad+' V'+(h-pad)+'" stroke="#557087" fill="none"/><path d="'+path+'" stroke="#52d6d0" stroke-width="3" fill="none" stroke-linejoin="round"/>'+xy.map(p=>'<circle cx="'+p[0]+'" cy="'+p[1]+'" r="4" fill="#52d6d0"/>').join("")+'<g fill="#9eb1c4" font-size="10"><text x="'+pad+'" y="'+(h-7)+'">0 s</text><text x="'+(w-pad)+'" y="'+(h-7)+'" text-anchor="end">'+maxT+' s</text><text x="4" y="12">'+maxF.toLocaleString()+' kN</text></g>';
}
function setupCurveEditor(box,initial){
 const body=box.querySelector("[data-curve-rows]");
 const add=(point=[0,1000])=>{
  const tr=document.createElement("tr");tr.setAttribute("data-curve-row","");
  tr.innerHTML='<td><input data-curve-time type="number" min="0" step="any" value="'+esc(point[0])+'"></td><td><input data-curve-thrust type="number" min="0.000001" step="any" value="'+esc(point[1])+'"></td><td><button type="button" class="curve-remove" data-curve-remove title="ลบจุดนี้">ลบ</button></td>';
  body.appendChild(tr);
 };
 (Array.isArray(initial)?initial:[]).forEach(add);
 box.querySelector("[data-curve-add]").addEventListener("click",()=>{
  const pts=curvePointsFromEditor(box),last=pts[pts.length-1]||[0,1000];add([last[0]+10,last[1]]);curveRefresh(box);
 });
 body.addEventListener("input",()=>curveRefresh(box));
 body.addEventListener("click",e=>{if(e.target.closest("[data-curve-remove]")){e.target.closest("tr").remove();curveRefresh(box)}});
 body.querySelectorAll(".curve-remove").forEach(b=>b.setAttribute("data-curve-remove",""));
 curveRefresh(box);
}
function fillDbChildFields(row={}){
 const kind=$("db-child-type").value;
 const notes=kind==="rocket_stages"?'<p class="note" style="grid-column:1/-1">Stage 1 ต้องมี Thrust SL เพื่อคำนวณ TWR ตอนเริ่มบิน ส่วน ISP SL เว้นได้และจะใช้ ISP vacuum เป็นค่าประมาณในบรรยากาศ</p>':kind==="rocket_boosters"?'<p class="note" style="grid-column:1/-1">Booster: Thrust SL และ ISP SL เว้นได้แยกกัน; ค่าที่ขาดจะใช้ Vacuum เป็นค่าประมาณ</p>':"";
 $("db-child-fields").innerHTML=notes+dbFields[kind].map(([key,label,type])=>type==="json"?'<section class="curve-editor" style="grid-column:1/-1"><div class="curve-head"><strong>Thrust-Time Curve</strong><span>เวลาเผาไหม้สะสม (s) · Thrust vacuum (kN)</span></div><input type="hidden" data-db-field="'+key+'"><div class="table-wrap"><table class="curve-table"><thead><tr><th>เวลา (s)</th><th>แรงขับ (kN)</th><th></th></tr></thead><tbody data-curve-rows></tbody></table></div><div class="admin-actions"><button type="button" class="curve-add" data-curve-add>＋ เพิ่มจุดข้อมูล</button></div><p class="note">เพิ่มจุดตามลำดับเวลา ระบบจะเชื่อมจุดด้วย Linear Interpolation และสร้าง JSON ให้อัตโนมัติ ไม่ต้องเขียนโค้ดเอง ค่าแรงขับต้องมากกว่า 0; การหยุดเครื่องยนต์กำหนดจาก Burn time / Mission Timeline</p><svg data-curve-chart viewBox="0 0 520 170" role="img" aria-label="กราฟแรงขับตามเวลา"></svg></section>':'<label>'+esc(label)+'<input data-db-field="'+key+'" type="'+type+'" value="'+esc(row[key]??"")+'" '+(key==="source_url"?'placeholder="https://..."':((kind==="rocket_stages"||kind==="rocket_boosters")&&(key==="thrust_sl_kn"||key==="isp_sl_s")?'placeholder="เว้นว่างได้"':""))+'></label>').join("");
 const curveBox=$("db-child-fields").querySelector(".curve-editor");
 if(curveBox)setupCurveEditor(curveBox,row.thrust_curve_json||[]);
}
function fillDbChildSelect(){
 const kind=$("db-child-type").value,vid=$("db-child-version").value;
 const rows=(catalogData?.[{rocket_stages:"stages",rocket_boosters:"boosters",rocket_sources:"sources"}[kind]]||[]).filter(x=>x.version_id===vid);
 $("db-child-select").innerHTML='<option value="">＋ เพิ่มรายการใหม่</option>'+rows.map(x=>'<option value="'+esc(x.id)+'">'+esc(x.name||x.title||("รายการ "+(x.stage_number??"")))+'</option>').join("");
 fillDbChildFields();
}
function fillDbVersionSelect(){
 const rid=$("db-version-rocket").value;
 const allVs=(catalogData?.versions||[]).filter(v=>v.rocket_id===rid);
 const vs=allVs.filter(v=>v.status==="draft");
 $("db-version-select").innerHTML='<option value="">＋ สร้าง Draft ใหม่</option>'+vs.map(v=>'<option value="'+esc(v.id)+'">Revision '+esc(v.revision)+' · '+esc(v.status)+'</option>').join("");
 const next=Math.max(0,...allVs.map(v=>Number(v.revision)||0))+1;
 $("db-revision").value=next;
 fillDbVersionForm();
 $("db-child-version").innerHTML=vs.map(v=>'<option value="'+esc(v.id)+'">Revision '+esc(v.revision)+' · '+esc(v.status)+'</option>').join("");
 fillDbChildSelect();
}
function fillDbVersionForm(){
 const v=(catalogData?.versions||[]).find(x=>x.id===$("db-version-select").value);
 $("db-revision").value=v?.revision??Math.max(1,...(catalogData?.versions||[]).filter(x=>x.rocket_id===$("db-version-rocket").value).map(x=>Number(x.revision)+1));
 $("db-confidence").value=v?.confidence||"D";
 $("db-capacity").value=v?.payload_capacity_leo_kg??"";
 $("db-fairing").value=v?.fairing_mass_kg??"";
 $("db-version-notes").value=v?.notes||"";
}
function refreshDbSelects(){
 if(!catalogData)return;
 const rockets=catalogData.rockets||[];
 const opts='<option value="">＋ สร้างจรวดใหม่</option>'+rockets.map(r=>'<option value="'+esc(r.id)+'">'+esc(r.name)+'</option>').join("");
 $("db-rocket-select").innerHTML=opts;
 $("db-version-rocket").innerHTML=rockets.map(r=>'<option value="'+esc(r.id)+'">'+esc(r.name)+'</option>').join("");
 if(!rockets.length){$("db-version-rocket").innerHTML='<option value="">ยังไม่มีจรวด</option>'}
 fillDbVersionSelect();
}
$("db-rocket-select").onchange=()=>{
 const r=(catalogData?.rockets||[]).find(x=>x.id===$("db-rocket-select").value);
 $("db-rocket-name").value=r?.name||"";$("db-rocket-slug").value=r?.slug||"";
 $("db-rocket-maker").value=r?.manufacturer||"";$("db-rocket-country").value=r?.country||"";
 $("db-rocket-type").value=r?.vehicle_type||"orbital";
};
$("db-version-rocket").onchange=fillDbVersionSelect;
$("db-version-select").onchange=fillDbVersionForm;
$("db-child-version").onchange=fillDbChildSelect;
$("db-child-type").onchange=fillDbChildSelect;
$("db-child-select").onchange=()=>{
 const kind=$("db-child-type").value,id=$("db-child-select").value;
 const key={rocket_stages:"stages",rocket_boosters:"boosters",rocket_sources:"sources"}[kind];
 const row=(catalogData?.[key]||[]).find(x=>x.id===id);
 fillDbChildFields(row||{});
};
$("db-save-rocket").onclick=async()=>{
 try{
  const id=dbVal("db-rocket-select"),payload={name:dbVal("db-rocket-name"),slug:dbVal("db-rocket-slug"),manufacturer:dbVal("db-rocket-maker")||null,country:dbVal("db-rocket-country")||null,vehicle_type:dbVal("db-rocket-type")};
  if(!payload.name||!payload.slug)throw Error("กรอกชื่อจรวดและ Slug ก่อน");
  const saved=id?await api("/admin/rockets/"+encodeURIComponent(id),"PATCH",payload):await api("/admin/rockets","POST",payload);
  status(id?"แก้ไขข้อมูลจรวดแล้ว":"เพิ่มจรวดแล้ว");await load();$("db-rocket-select").value=saved.id;$("db-rocket-select").dispatchEvent(new Event("change"));
 }catch(e){status(e.message)}
};
$("db-save-version").onclick=async()=>{
 try{
  const rid=dbVal("db-version-rocket"),id=dbVal("db-version-select");
  if(!rid)throw Error("เลือกจรวดก่อน");
  const payload={revision:dbNum("db-revision"),confidence:dbVal("db-confidence"),payload_capacity_leo_kg:dbNum("db-capacity"),fairing_mass_kg:dbNum("db-fairing"),notes:dbVal("db-version-notes")||null};
  Object.keys(payload).forEach(k=>{if(payload[k]===null)delete payload[k]});
  const saved=id?await api("/admin/versions/"+encodeURIComponent(id),"PATCH",payload):await api("/admin/rockets/"+encodeURIComponent(rid)+"/versions","POST",payload);
  status(id?"แก้ไข Revision แล้ว":"สร้าง Draft Revision แล้ว");await load();$("db-version-rocket").value=rid;fillDbVersionSelect();$("db-version-select").value=saved.id;fillDbVersionForm();
 }catch(e){status(e.message)}
};
$("db-save-child").type="button";
$("db-save-child").addEventListener("click",async()=>{
 const button=$("db-save-child"),label=button.textContent;
 button.disabled=true;button.textContent="กำลังบันทึก...";status("กำลังส่งข้อมูลไปยังฐานข้อมูล...");
 try{
  const vid=dbVal("db-child-version"),kind=$("db-child-type").value,id=dbVal("db-child-select");
  if(!vid)throw Error("ยังไม่มี Draft Revision · กรุณาสร้างหรือเลือก Draft ก่อน");
  const curveBox=$("db-child-fields").querySelector(".curve-editor");
  if(curveBox){
   const points=curvePointsFromEditor(curveBox);
   if(points.length&& (points.length<2||points[0][0]!==0||points.some((p,i)=>!Number.isFinite(p[0])||!Number.isFinite(p[1])||p[0]<0||p[1]<=0||(i>0&&p[0]<=points[i-1][0]))))throw Error("Thrust-Time Curve ต้องมีอย่างน้อย 2 จุด เริ่มที่ 0 วินาที ใช้แรงขับมากกว่า 0 และเวลาเพิ่มขึ้นทุกจุด");
  }
  const payload={};$("db-child-fields").querySelectorAll("[data-db-field]").forEach(el=>{const v=el.value.trim();if(v!=="")payload[el.dataset.dbField]=el.dataset.dbField==="thrust_curve_json"?JSON.parse(v):(el.type==="number"?Number(v):v)});
  if(curveBox)payload.thrust_curve_json=points.length?points:null;
  if(kind==="rocket_stages"){
   for(const key of ["thrust_sl_kn","isp_sl_s"])if(!(key in payload))payload[key]=null;
   if(!payload.stage_number)throw Error("กรอกลำดับ Stage");
   const a=payload.thrust_sl_kn!==null,b=payload.isp_sl_s!==null;
   if(Number(payload.stage_number)===1&&!a)throw Error("Stage 1 ต้องมี Thrust SL เพื่อคำนวณ TWR ตอนเริ่มบิน");
  }
  if(kind==="rocket_boosters"){
   for(const key of ["thrust_sl_kn","isp_sl_s"])if(!(key in payload))payload[key]=null;

  }
  if(kind==="rocket_sources"&&!payload.title)throw Error("กรอกชื่อแหล่งข้อมูล");
  const saved=id?await api("/admin/"+kind+"/"+encodeURIComponent(id),"PATCH",payload):await api("/admin/versions/"+encodeURIComponent(vid)+"/"+kind,"POST",payload);
  status(id?"บันทึกการแก้ไขสำเร็จ":"เพิ่มรายการสำเร็จ");
  await load();$("db-child-version").value=vid;fillDbChildSelect();if(saved.id)$("db-child-select").value=saved.id;$("db-child-select").dispatchEvent(new Event("change"));
 }catch(e){status("บันทึกไม่สำเร็จ: "+(e?.message||String(e)));$("status").scrollIntoView({behavior:"smooth",block:"center"})}
 finally{button.disabled=false;button.textContent=label}
 });;

show();if(token)load().catch(e=>{status(e.message);token="";sessionStorage.removeItem("rp_admin_token");show()});

$("db-publish-version").onclick=async()=>{
 try{
  const id=dbVal("db-version-select");
  if(!id)throw Error("เลือก Draft Revision ที่ต้องการเผยแพร่ก่อน");
  const version=(catalogData?.versions||[]).find(v=>v.id===id);
  if(!version||version.status!=="draft")throw Error("เผยแพร่ได้เฉพาะ Draft เท่านั้น");
  if(!confirm("ยืนยันเผยแพร่ Revision "+version.revision+"? ข้อมูลนี้จะกลายเป็นเวอร์ชันสาธารณะ"))return;
  await api("/admin/versions/"+encodeURIComponent(id)+"/publish","POST");
  status("เผยแพร่ Revision สำเร็จ");await load();
 }catch(e){status(e.message)}
};
