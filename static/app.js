const $=id=>document.getElementById(id);
let lastResult=null,lastPayload=null,mapObj=null;
function setVal(id,v){if(v!==undefined&&v!==null&&$(id))$(id).value=v}
function stageTimeline(stages){let t=0;return stages.map(s=>{const ign=t+Number(s.ignition_delay||0),cut=ign+Number(s.burn_time),sep=cut+2;t=sep;return {ignition_t:ign,cutoff_t:cut,separation_t:sep,burns:[{ignition_t:ign,cutoff_t:cut}]}})}
function applyConfig(p){
 for(const k of ["payload","fairing_mass","fairing_alt","site_lat","site_lon","site_alt","target_alt","target_apogee_alt","launch_azimuth_deg","mission_type","vertical_time","kick_angle","kick_duration"])setVal(k,p[k]);
 $("stages").value=JSON.stringify(p.stages||[],null,2);
 $("boost_groups").value=JSON.stringify(p.boost_groups||[],null,2);
 $("use_boost").checked=!!p.use_boost;
 $("boost-fields").classList.toggle("hidden",!p.use_boost);
 setVal("boost_throttle",p.boost_throttle??100);setVal("solo_throttle",p.solo_throttle??100);
 $("boost_auto_burn").checked=p.boost_auto_burn!==false;
 for(const k of ["obs_lat","obs_lon","obs_alt","min_elevation","timestep","orbit_count"])setVal(k,p[k]);
 if(p.auto_profile!==undefined){$("auto_profile").checked=!!p.auto_profile;$("manual-profile").classList.toggle("hidden",!!p.auto_profile)}
 $("mission_type").value=p.mission_type||"circular";
 $("target_apogee_alt").disabled=$("mission_type").value==="circular";
}
$("mission_type").addEventListener("change",()=>{$("target_apogee_alt").disabled=$("mission_type").value==="circular"});
$("use_boost").addEventListener("change",()=> $("boost-fields").classList.toggle("hidden",!$("use_boost").checked));
$("use_timeline").addEventListener("change",()=>{$("timeline-fields").classList.toggle("hidden",!$("use_timeline").checked);if($("use_timeline").checked){try{$("timeline_stages").value=JSON.stringify(stageTimeline(JSON.parse($("stages").value)),null,2)}catch(e){}}});
$("auto_profile").addEventListener("change",()=> $("manual-profile").classList.toggle("hidden",$("auto_profile").checked));
function download(name,content,type){const blob=new Blob([content],{type}),url=URL.createObjectURL(blob),a=document.createElement("a");a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();URL.revokeObjectURL(url)}
function n(id){return Number($(id).value)}
function safe(v,d=2){return v===null||v===undefined||!Number.isFinite(Number(v))?"—":Number(v).toFixed(d)}
function metric(label,value,sub=""){return `<div class="metric"><span>${label}</span><strong>${value}</strong><small>${sub}</small></div>`}
function csv(rows){if(!rows||!rows.length)return "";const keys=Object.keys(rows[0]);const q=x=>{if(x===null||x===undefined)return "";const s=String(x);return /[",\n]/.test(s)?'"'+s.replace(/"/g,'""')+'"':s};return [keys.map(q).join(","),...rows.map(r=>keys.map(k=>q(r[k])).join(","))].join("\n")}
function svgSkyChart(id,rows,minEl){
 const el=$(id);if(!el)return;
 const source=Array.isArray(rows)?rows:[];
 const visible=source.filter(r=>Number.isFinite(Number(r.az_deg))&&Number.isFinite(Number(r.el_deg))&&Number(r.el_deg)>Number(minEl));
 if(!visible.length){el.innerHTML='<p class="hint">ไม่มีช่วงที่ผ่านมุมเงยขั้นต่ำ</p>';return}
 const maxPoints=1200,step=Math.max(1,Math.ceil(visible.length/maxPoints)),v=visible.filter((_,i)=>i%step===0||i===visible.length-1);
 const W=420,cx=210,cy=170,rad=132;
 let z='<svg viewBox="0 0 420 350" role="img" aria-label="แผนภาพทิศและมุมเงยของจรวด" style="width:100%;height:auto;display:block">';
 [30,60,90].forEach(e=>{const r=rad*(90-e)/90;z+='<circle cx="'+cx+'" cy="'+cy+'" r="'+r+'" fill="none" stroke="#35485d"/><text x="'+(cx+6)+'" y="'+(cy-r+13)+'" fill="#9fb2c5" font-size="10">'+e+'°</text>'});
 [["N",0],["E",90],["S",180],["W",270]].forEach(([t,a])=>{const q=a*Math.PI/180;z+='<text x="'+(cx+Math.sin(q)*(rad+18))+'" y="'+(cy-Math.cos(q)*(rad+18)+4)+'" text-anchor="middle" fill="#dce8f3" font-size="12">'+t+'</text>'});
 let d='';v.forEach((p,i)=>{const a=Number(p.az_deg)*Math.PI/180,r=rad*(90-Number(p.el_deg))/90;d+=(i?' L':'M')+(cx+Math.sin(a)*r).toFixed(1)+','+(cy-Math.cos(a)*r).toFixed(1)});
 const first=v[0],last=v[v.length-1],point=p=>{const a=Number(p.az_deg)*Math.PI/180,r=rad*(90-Number(p.el_deg))/90;return [cx+Math.sin(a)*r,cy-Math.cos(a)*r]};
 const fp=point(first),lp=point(last);
 z+='<path d="'+d+'" fill="none" stroke="#ff8b59" stroke-width="3" stroke-linejoin="round"/><circle cx="'+fp[0].toFixed(1)+'" cy="'+fp[1].toFixed(1)+'" r="4" fill="#53d5d0"/><circle cx="'+lp[0].toFixed(1)+'" cy="'+lp[1].toFixed(1)+'" r="4" fill="#ff8b59"/><text x="18" y="330" fill="#53d5d0" font-size="11">● เริ่มเห็น</text><text x="105" y="330" fill="#ff8b59" font-size="11">● สิ้นสุด</text></svg>';
 el.innerHTML=z;
}

function renderSkySafely(rows,minEl){
 try{svgSkyChart("sky-chart",rows,minEl)}
 catch(err){const el=$("sky-chart");if(el)el.innerHTML='<p class="hint">แผนภาพท้องฟ้าแสดงผลไม่ได้: '+escapeHtml(err.message||String(err))+'</p>';console.error("Sky view render failed",err)}
}
function splitTrack(points){
 const out=[];let seg=[];
 const normLon=x=>{let v=((Number(x)+180)%360+360)%360-180;return Object.is(v,-0)?0:v};
 for(const point of points){
  const lat=Number(point[0]),lon=normLon(point[1]);
  if(!Number.isFinite(lat)||!Number.isFinite(lon))continue;
  if(seg.length){
   const prev=seg[seg.length-1],delta=lon-prev[1];
   if(Math.abs(delta)>180){
    const eastward=delta< -180, edge=eastward?180:-180;
    const unwrapped=lon+(eastward?360:-360);
    const f=(edge-prev[1])/(unwrapped-prev[1]);
    const crossLat=prev[0]+(lat-prev[0])*f;
    seg.push([crossLat,edge]);
    if(seg.length>1)out.push(seg);
    seg=[ [crossLat,-edge], [lat,lon] ];
    continue;
   }
  }
  seg.push([lat,lon]);
 }
 if(seg.length>1)out.push(seg);
 return out;
}
function renderGroundTrackFallback(el,asc,orb,p){
 const W=960,H=480,project=pt=>[(Number(pt[1])+180)/360*W,(90-Math.max(-90,Math.min(90,Number(pt[0]))))/180*H];
 const path=points=>splitTrack(points).map(seg=>seg.map((pt,i)=>{const q=project(pt);return (i?"L":"M")+q[0].toFixed(1)+","+q[1].toFixed(1)}).join(" ")).join(" ");
 let grid="";
 for(let lon=-180;lon<=180;lon+=30){const x=(lon+180)/360*W;grid+='<line x1="'+x+'" y1="0" x2="'+x+'" y2="'+H+'" stroke="#26384d"/><text x="'+x+'" y="18" fill="#9fb2c5" font-size="12" text-anchor="middle">'+lon+'°</text>'}
 for(let lat=-60;lat<=60;lat+=30){const y=(90-lat)/180*H;grid+='<line x1="0" y1="'+y+'" x2="'+W+'" y2="'+y+'" stroke="#26384d"/><text x="8" y="'+(y-5)+'" fill="#9fb2c5" font-size="12">'+lat+'°</text>'}
 const launch=project([p.site_lat,p.site_lon]),observer=project([p.obs_lat,p.obs_lon]);
 el.innerHTML='<svg viewBox="0 0 '+W+' '+H+'" role="img" aria-label="Ground track on latitude longitude grid" style="width:100%;height:100%;min-height:260px;display:block;background:#091523">'+grid+
 '<path d="'+path(asc)+'" fill="none" stroke="#ff8b59" stroke-width="3" stroke-linejoin="round"/>'+
 '<path d="'+path(orb)+'" fill="none" stroke="#53d5d0" stroke-width="2.5" stroke-dasharray="7 5" stroke-linejoin="round"/>'+
 '<circle cx="'+launch[0]+'" cy="'+launch[1]+'" r="6" fill="#f5c76b"/><circle cx="'+observer[0]+'" cy="'+observer[1]+'" r="6" fill="#ffffff"/>'+
 '<text x="18" y="'+(H-18)+'" fill="#9fb2c5" font-size="13">แผนที่สำรองแบบพิกัดละติจูด/ลองจิจูด · เมื่อแผนที่ออนไลน์ไม่พร้อมใช้งาน</text></svg>';
}
function drawMap(data,p){
 const el=$("map");if(!el)return;
 const ascent=Array.isArray(data.ascent)?data.ascent:[],orbit=Array.isArray(data.orbit)?data.orbit:[];
 const asc=ascent.filter(x=>Number.isFinite(Number(x.lat))&&Number.isFinite(Number(x.lon))).map(x=>[Number(x.lat),Number(x.lon)]);
 const orb=orbit.filter(x=>Number.isFinite(Number(x.lat))&&Number.isFinite(Number(x.lon))).map(x=>[Number(x.lat),Number(x.lon)]);
 if(!asc.length&&!orb.length){el.innerHTML='<p class="hint">ไม่มีพิกัดเส้นทางสำหรับแสดงแผนที่</p>';return}
 try{
  if(mapObj){mapObj.remove();mapObj=null}
  if(!window.L||typeof L.map!=="function"){renderGroundTrackFallback(el,asc,orb,p);return}
  mapObj=L.map(el,{worldCopyJump:true}).setView([0,0],2);
  const tiles=L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{attribution:"© OpenStreetMap",maxZoom:18});
  let tileErrors=0;
  tiles.on("tileerror",()=>{tileErrors++;if(tileErrors>=3&&mapObj){try{mapObj.remove()}catch(_){}mapObj=null;renderGroundTrackFallback(el,asc,orb,p)}});
  tiles.addTo(mapObj);
  splitTrack(asc).forEach(seg=>L.polyline(seg,{color:"#ff8b59",weight:3}).addTo(mapObj));
  splitTrack(orb).forEach(seg=>L.polyline(seg,{color:"#53d5d0",weight:2,dashArray:"6 5"}).addTo(mapObj));
  if(Number.isFinite(Number(p.site_lat))&&Number.isFinite(Number(p.site_lon)))L.marker([p.site_lat,p.site_lon]).addTo(mapObj).bindPopup("Launch site");
  if(Number.isFinite(Number(p.obs_lat))&&Number.isFinite(Number(p.obs_lon)))L.marker([p.obs_lat,p.obs_lon]).addTo(mapObj).bindPopup("Observer");
  // Keep a stable world view: fitting a combined ascent + multi-orbit track
  // can choose a nearly 360-degree longitude span and visually stretch the route.
  requestAnimationFrame(()=>mapObj&&mapObj.invalidateSize());
 }catch(err){console.error("Ground track render failed",err);if(mapObj){try{mapObj.remove()}catch(_){}mapObj=null}renderGroundTrackFallback(el,asc,orb,p)}
}
function escapeHtml(value){return String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
function tableRows(selector,rows,cols){
 const target=document.querySelector(selector.startsWith("#")?selector:`#${selector}`);if(!target)return;
 const data=Array.isArray(rows)?rows:[];
 target.innerHTML=data.map(r=>"<tr>"+cols.map(c=>"<td>"+escapeHtml(typeof c==="function"?c(r):r[c])+"</td>").join("")+"</tr>").join("");
}
function sampleRows(rows,interval=10){
 if(!Array.isArray(rows)||!rows.length)return [];
 const out=[];let bucket=-1;
 rows.forEach(r=>{const t=Number(r.t);if(!Number.isFinite(t))return;const b=Math.floor(t/interval);if(b!==bucket){out.push(r);bucket=b}});
 if(out[out.length-1]!==rows[rows.length-1])out.push(rows[rows.length-1]);
 return out;
}
function render(data,p){
 lastResult=data;lastPayload=p;$("welcome").classList.add("hidden");$("loading").classList.add("hidden");$("error").classList.add("hidden");$("output").classList.remove("hidden");
 const s=data.summary,e=data.elements,v=data.visibility;
 $("metrics").innerHTML=
 metric("LIFTOFF MASS",safe(s.gross_mass_kg/1000,1)+" t")+
 metric("MECO","T+"+safe(s.meco_s,0)+" s")+
 metric("MAX-Q",safe(s.max_q_kpa,1)+" kPa","T+"+safe(s.max_q_time_s,0)+" s")+
 metric("MAX ACCELERATION",safe(s.max_g,2)+" g")+
 metric("LAUNCH AZIMUTH",safe(s.azimuth_rotating_deg,1)+"°","Earth-fixed")+
 metric("ORBITAL ΔV",safe(s.delta_v_mps,0)+" m/s")+
 metric("PERIGEE",safe(e.perigee_km,1)+" km")+
 metric("APOGEE",e.apogee_km===null?"Escape":safe(e.apogee_km,1)+" km")+
 metric("ORBIT INCLINATION",safe(e.inc_deg,2)+"°")+
 metric("VISIBLE DURATION",safe(s.visible_duration_s,0)+" s")+
 metric("ROCKET SUNLIT",safe(s.sunlit_percent,0)+"%")+
 metric("PHOTO WINDOW",safe(s.photo_window_percent,0)+"%");
 const warn=[...(data.model_warnings||[])];if(p.mission_type==="escape"&&e.e<1)warn.push("พลังงานยังไม่พอหลุดพ้นโลก (e < 1)");if(e.e>=1)warn.push("Escape trajectory: orbital eccentricity ≥ 1");if(data.boost_warnings?.length)warn.push(...data.boost_warnings);if(s.visible_count===0)warn.push("ไม่พบช่วงที่จรวดสูงกว่ามุมเงยขั้นต่ำจากตำแหน่งผู้ชม");$("warnings").innerHTML=warn.length?'<div class="notice">'+warn.map(x=>"⚠ "+x).join("<br>")+"</div>":"";
 drawMap(data,p);
 tableRows("events-table tbody",data.events||[],[r=>r.event,r=>safe(r.t,1),r=>safe(r.alt_km,1),r=>safe(r.velocity_mps,0)]);
 const bp=$("boost-panel");if(data.boost_log?.length){bp.classList.remove("hidden");tableRows("boost-table tbody",data.boost_log,[r=>safe(r.t0,1)+"–"+safe(r.t1,1),r=>r.name,r=>safe(r.F_sl,0)+" kN",r=>safe(r.isp_vac,1),r=>safe(r.prop/1000,2)+" t",r=>safe(r.jett/1000,2)+" t"])}else bp.classList.add("hidden");
 const a=Array.isArray(data.ascent)?data.ascent:[],l=Array.isArray(data.look)?data.look:[];
 const ascentSamples=sampleRows(a,10);
 tableRows("ascent-table tbody",ascentSamples,[
  r=>safe(r.t,1),r=>safe(r.alt_km,2),r=>safe(r.v_relative,0),r=>safe(r.mach,2),
  r=>safe(r.q_kPa,2),r=>safe(r.fpa_deg,2),r=>safe(r.acc_g,2),
  r=>safe(r.mass,0),r=>safe(r.thrust_kN,0),r=>r.stage||"—"
 ]);
 const vis=l.filter(x=>x.el_deg>p.min_elevation);
 const cards=[["FIRST VISIBLE",v.first?.t!==undefined?"T+"+safe(v.first.t,1)+" s":"—"],["PEAK ELEVATION",v.peak?safe(v.peak.el_deg,1)+"°":"—"],["CLOSEST RANGE",v.closest?safe(v.closest.range_km,1)+" km":"—"],["LAST VISIBLE",v.last?.t!==undefined?"T+"+safe(v.last.t,1)+" s":"—"],["SUNLIT WHILE VISIBLE",safe(s.sunlit_percent,0)+"%"],["TWILIGHT PHOTO WINDOW",safe(s.photo_window_percent,0)+"%"]];
 $("visibility").innerHTML=cards.map(([k,x])=>`<div class="vis-item"><span>${k}</span><b>${x}</b></div>`).join("");
 $("report").textContent=data.report;
  renderSkySafely(l,p.min_elevation);

  const table=sampleRows(vis,10);tableRows("look-table tbody",table,[r=>safe(r.t,1),r=>safe(r.az_deg,2),r=>safe(r.el_deg,2),r=>safe(r.range_km,2),r=>safe(r.alt_km,2),r=>safe(r.angular_rate,3)]);
 const entries=[["Semi-major axis",e.a_km,"km"],["Eccentricity",e.e,""],["Inclination",e.inc_deg,"°"],["RAAN",e.raan_deg,"°"],["Argument of periapsis",e.argp_deg,"°"],["True anomaly",e.ta_deg,"°"],["Orbital period",e.period_min,"min"],["Earth rotation bonus",s.earth_rotation_bonus_mps,"m/s"]];
 $("elements").innerHTML=entries.map(([k,x,u])=>`<div class="element"><span>${k}</span><b>${x===null?"—":safe(x,2)+u}</b></div>`).join("");
}
function buildKml(data){const placemark=(name,pts,color)=>{const lines=splitTrack(pts.map(x=>[x.lat,x.lon,x.alt_km*1000]));return lines.map(seg=>`<Placemark><name>${name}</name><Style><LineStyle><color>${color}</color><width>3</width></LineStyle></Style><LineString><altitudeMode>absolute</altitudeMode><coordinates>${seg.map(x=>x[1].toFixed(6)+","+x[0].toFixed(6)+","+x[2].toFixed(1)).join(" ")}</coordinates></LineString></Placemark>`).join("")};return '<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>Rocket Planner trajectory</name>'+placemark("Ascent",data.ascent,"ff598bff")+placemark("Orbit",data.orbit,"ffd0d653")+"</Document></kml>"}
$("export-ascent").addEventListener("click",()=>lastResult&&download("ascent.csv",csv(lastResult.ascent),"text/csv"));
$("export-look").addEventListener("click",()=>lastResult&&download("look_angles.csv",csv(lastResult.look),"text/csv"));
$("export-orbit").addEventListener("click",()=>lastResult&&download("orbit.csv",csv(lastResult.orbit),"text/csv"));
$("export-kml").addEventListener("click",()=>lastResult&&download("trajectory.kml",buildKml(lastResult),"application/vnd.google-earth.kml+xml"));
$("export-elements").addEventListener("click",()=>lastResult&&download("elements.json",JSON.stringify(lastResult.elements,null,2),"application/json"));
$("export-report").addEventListener("click",()=>lastResult&&download("observation_report.txt",lastResult.report,"text/plain;charset=utf-8"));
$("mission-form").addEventListener("submit",async ev=>{
 ev.preventDefault();$("welcome").classList.add("hidden");$("output").classList.add("hidden");$("error").classList.add("hidden");$("loading").classList.remove("hidden");
 let stages,boostGroups=[],timeline=null;
 try{stages=JSON.parse($("stages").value);if(!Array.isArray(stages)||!stages.length||stages.length>5)throw Error("Stages ต้องเป็น JSON array จำนวน 1–5 สเตจ");if($("use_boost").checked){boostGroups=JSON.parse($("boost_groups").value||"[]");if(!Array.isArray(boostGroups)||!boostGroups.length||boostGroups.length>4)throw Error("Booster groups ต้องเป็น JSON array จำนวน 1–4 กลุ่ม")}if($("use_timeline").checked){const tStages=JSON.parse($("timeline_stages").value);if(!Array.isArray(tStages))throw Error("Timeline ต้องเป็น JSON array");timeline={stages:tStages,fairing_t:$("fairing_t").value===""?null:n("fairing_t"),payload_t:$("payload_t").value===""?null:n("payload_t")}}}catch(err){$("loading").classList.add("hidden");$("error").textContent="Input error: "+err.message;$("error").classList.remove("hidden");return}
 const launch=$("launch_utc").value;if(!launch){$("loading").classList.add("hidden");$("error").textContent="กรุณาระบุ Launch UTC";$("error").classList.remove("hidden");return}
 const p={stages,payload:n("payload"),fairing_mass:n("fairing_mass"),fairing_alt:n("fairing_alt"),site_lat:n("site_lat"),site_lon:n("site_lon"),site_alt:n("site_alt"),obs_lat:n("obs_lat"),obs_lon:n("obs_lon"),obs_alt:n("obs_alt"),target_alt:n("target_alt"),target_apogee_alt:n("target_apogee_alt"),launch_azimuth_deg:n("launch_azimuth_deg"),mission_type:$("mission_type").value,launch_utc:launch+":00Z",auto_profile:$("auto_profile").checked,vertical_time:n("vertical_time"),kick_angle:n("kick_angle"),kick_duration:n("kick_duration"),min_elevation:n("min_elevation"),timestep:n("timestep"),orbit_count:n("orbit_count"),use_boost:$("use_boost").checked,boost_groups:boostGroups,boost_throttle:n("boost_throttle"),solo_throttle:n("solo_throttle"),boost_auto_burn:$("boost_auto_burn").checked,use_timeline:$("use_timeline").checked,timeline};
 try{const r=await fetch("/api/simulate",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(p)});const d=await r.json();if(!r.ok)throw Error(d.detail||"API error");render(d,p)}catch(err){$("loading").classList.add("hidden");$("error").textContent="Simulation error: "+err.message;$("error").classList.remove("hidden")}
});


// Published Supabase rocket catalog integration. Rocket selection is database-only.
let databaseRockets = [];
async function loadDatabaseRockets() {
  const select = $("database-rocket");
  if (!select) return;
  try {
    const response = await fetch("/api/public/rockets");
    const data = await response.json();
    if (!response.ok) throw Error(data.detail || "Database unavailable");
    databaseRockets = Array.isArray(data) ? data : [];
    select.innerHTML = '<option value="">— เลือกจรวดจากฐานข้อมูล —</option>' +
      databaseRockets.map((r, i) => '<option value="' + i + '">' +
        String(r.name || r.slug || ("Rocket " + (i + 1))).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])) +
        '</option>').join("");
    $("database-status").textContent = databaseRockets.length
      ? "พบจรวดที่เผยแพร่ " + databaseRockets.length + " รายการ"
      : "ยังไม่มีจรวดที่เผยแพร่ในฐานข้อมูล";
  } catch (error) {
    select.innerHTML = '<option value="">ฐานข้อมูลยังไม่พร้อมใช้งาน</option>';
    $("database-status").textContent = error.message + "";
  }
}
function loadDatabaseRocket() {
  const selected = $("database-rocket").value;
  if (selected === "") return;
  const index = Number(selected);
  if (!Number.isInteger(index) || !databaseRockets[index]) return;
  const rocket = databaseRockets[index];
  const version = rocket.current_version || {};
  // Convert Supabase column names/units to the simulation API contract.
  const stages = (version.stages || []).map((stage, i) => ({
    name: stage.name || "Stage " + (stage.stage_number ?? i + 1),
    thrust_sl: stage.thrust_sl_kn ?? null,
    thrust_vac: stage.thrust_vac_kn,
    isp_sl: stage.isp_sl_s ?? null,
    isp_vac: stage.isp_vac_s,
    prop_mass: stage.prop_mass_kg,
    dry_mass: stage.dry_mass_kg,
    burn_time: stage.burn_time_s,
    area: stage.reference_area_m2,
    ignition_delay: stage.ignition_delay_s ?? 0,
    thrust_curve: stage.thrust_curve_json ?? null,
  }));
  if (!stages.length) {
    $("stages").value = "[]";
    $("boost_groups").value = "[]";
    $("use_boost").checked = false;
    $("boost-fields").classList.add("hidden");
    $("database-status").textContent = "รายการนี้ยังไม่มี Stage data จึงยังนำไปจำลองไม่ได้";
    return;
  }
  const boosters = (version.boosters || []).map(booster => ({
    name: booster.name || "SRB",
    count: booster.quantity,
    thrust_sl: booster.thrust_sl_kn ?? null,
    thrust_vac: booster.thrust_vac_kn,
    isp_sl: booster.isp_sl_s ?? null,
    isp_vac: booster.isp_vac_s,
    prop_mass: booster.prop_mass_kg,
    dry_mass: booster.dry_mass_kg,
    burn_time: booster.burn_time_s,
    area: booster.reference_area_m2,
    ignite_t: booster.ignite_t_s ?? 0,
    jettison_delay: booster.jettison_delay_s ?? 2,
    thrust_curve: booster.thrust_curve_json ?? null,
  }));
  const config = {
    ...version,
    stages,
    boost_groups: boosters,
    use_boost: boosters.length > 0,
    payload: version.payload ?? version.payload_mass_kg ?? version.payload_mass ?? 0,
    fairing_mass: version.fairing_mass_kg ?? version.fairing_mass ?? 0,
    fairing_alt: version.fairing_alt ?? version.fairing_jettison_alt_km ?? 110,
    target_alt: version.target_alt ?? 550,
    target_apogee_alt: version.target_apogee_alt ?? version.target_alt ?? 550,
    mission_type: version.mission_type ?? "circular",
    site_lat: version.site_lat ?? n("site_lat"),
    site_lon: version.site_lon ?? n("site_lon"),
    site_alt: version.site_alt ?? n("site_alt"),
  };
  applyConfig(config);
  $("database-status").textContent = "โหลด " + (rocket.name || rocket.slug) +
    " · Revision " + (version.version || version.version_number || version.id || "current");
}
$("database-rocket")?.addEventListener("change", loadDatabaseRocket);
loadDatabaseRockets();
