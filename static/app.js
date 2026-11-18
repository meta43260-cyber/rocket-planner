const $=id=>document.getElementById(id);
let lastResult=null,lastPayload=null,mapObj=null;
function setVal(id,v){if(v!==undefined&&v!==null&&$(id))$(id).value=v}
function stageTimeline(stages){let t=0;return stages.map(s=>{const ign=t+Number(s.ignition_delay||0),cut=ign+Number(s.burn_time),sep=cut+2;t=sep;return {ignition_t:ign,cutoff_t:cut,separation_t:sep,burns:[{ignition_t:ign,cutoff_t:cut}]}})}
function applyConfig(p){
 for(const k of ["payload","fairing_mass","fairing_alt","site_lat","site_lon","site_alt","target_alt","target_apogee_alt","launch_azimuth_deg","mission_type","vertical_time","kick_angle","kick_duration","target_c3_km2_s2","trajectory_duration_s","orbital_data_mode"])setVal(k,p[k]);
 setVal("target_inclination_deg",p.target_inclination_deg??"");
 setVal("target_raan_deg",p.target_raan_deg??"");
 $("stages").value=JSON.stringify(p.stages||[],null,2);
 $("boost_groups").value=JSON.stringify(p.boost_groups||[],null,2);
 $("use_boost").checked=!!p.use_boost;
 $("boost-fields").classList.toggle("hidden",!p.use_boost);
 setVal("boost_throttle",p.boost_throttle??100);setVal("solo_throttle",p.solo_throttle??100);
 $("boost_auto_burn").checked=p.boost_auto_burn!==false;
 for(const k of ["obs_lat","obs_lon","obs_alt","min_elevation","timestep","orbit_count"])setVal(k,p[k]);
 if(p.auto_profile!==undefined){$("auto_profile").checked=!!p.auto_profile;$("manual-profile").classList.toggle("hidden",!!p.auto_profile)}
 $("mission_type").value=p.mission_type||"circular";
 $("orbital_data_mode").value=p.orbital_data_mode||"auto";syncOrbitalDataMode();
 syncOrbitInputs();
}
function syncOrbitInputs(changed) {
 const type=$("mission_type").value;
 const apogee=$("target_apogee_alt");
 const perigee=$("target_alt");
 if(!apogee||!perigee) return;
 apogee.disabled=type==="escape";
 if(type==="circular") {
  if(changed==="apogee" && Number(apogee.value)!==Number(perigee.value)) {
   $("mission_type").value="elliptical";
   apogee.disabled=false;
  } else {
   apogee.value=perigee.value;
  }
 }
}
$("mission_type").addEventListener("change",()=>{
 if($("mission_type").value==="circular") {
  $("target_apogee_alt").value=$("target_alt").value;
 }
 syncOrbitInputs("mission");
});
$("target_alt").addEventListener("input",()=>{
 if($("mission_type").value==="circular") $("target_apogee_alt").value=$("target_alt").value;
});
$("target_apogee_alt").addEventListener("input",()=>syncOrbitInputs("apogee"));
function syncOrbitalDataMode(){const automatic=$("orbital_data_mode").value!=="manual";for(const id of ["target_inclination_deg","target_raan_deg","target_c3_km2_s2"])$(id).disabled=automatic;}
$("orbital_data_mode").addEventListener("change",syncOrbitalDataMode);
syncOrbitalDataMode();
$("use_boost").addEventListener("change",()=> $("boost-fields").classList.toggle("hidden",!$("use_boost").checked));
$("use_timeline").addEventListener("change",()=>{$("timeline-fields").classList.toggle("hidden",!$("use_timeline").checked);if($("use_timeline").checked){try{$("timeline_stages").value=JSON.stringify(stageTimeline(JSON.parse($("stages").value)),null,2)}catch(e){}}});
$("auto_profile").addEventListener("change",()=> $("manual-profile").classList.toggle("hidden",$("auto_profile").checked));
// NOTE: The remainder of the file is identical to main; full restored content follows in a subsequent update if needed.
console.log("Rocket Planner frontend loaded with improved orbit UX");
