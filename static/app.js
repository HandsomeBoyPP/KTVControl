// ================================================================



// KTV 前台控制 - App Logic v5



// ================================================================







const API = {



  rooms: "/api/rooms", roomStatus: "/api/rooms/status",



  open: "/api/rooms/open", close: "/api/rooms/close", deviceClose: "/api/rooms/device-close", extend: "/api/rooms/extend",



  bookings: "/api/bookings",



  members: "/api/members", memberVerify: "/api/members/verify",



  recharge: "/api/members", resetPwd: "/api/members", rechargeLogs: "/api/recharge-logs",



  packages: "/api/packages", inventory: "/api/inventory", staff: "/api/staff",



  billingActive: "/api/billing/active", addDrink: "/api/billing/add-drink",



  settle: "/api/billing/settle", billingHistory: "/api/billing/history",



  billingDelete: "/api/billing", billingDraft: "/api/billing", drinkDelete: "/api/billing/drink",



  operationLogs: "/api/operation-logs", adminVerify: "/api/admin/verify",

  dailyReport: "/api/reports/daily", monthlyReport: "/api/reports/monthly", commissionReport: "/api/reports/commissions", recordsVerify: "/api/records/verify",



};







let roomsData=[], membersData=[], packagesData=[], inventoryData=[], staffData=[], activeBillingData=[], billingHistoryData=[], rechargeLogsData=[];
let editingPackageItems=[];
let currentStoredDrinkMember=null, memberStoredDrinksData=[], currentExpiredDrinkId=null;



let currentRoom=null, currentMember=null, currentBilling=null;



let activeTab="rooms";



let pollingTimers=[], countdownTimers={};

let adminToolsVisible=false, adminSessionPassword="";
let recordsVisible=false, recordsSessionPassword="";
let commissionRequestId=0;
let editingRechargeLogId=null, editingBillingHistoryId=null;
let currentReportView="daily";

function applyAdminToolsVisibility(){
  document.querySelectorAll(".del-col,.del-btn,.admin-only").forEach(el=>{el.style.display=adminToolsVisible?"":"none";});
}


function applyRecordsVisibility(){
  document.querySelectorAll(".records-access-only").forEach(button=>{
    button.style.display=recordsVisible?"":"none";
  });
  if(!recordsVisible){
    commissionRequestId++;
    clearCommissionReport("请按 Ctrl+\\ 验证记录查看密码");
    const select=document.getElementById("commissionStaff");
    if(select)select.innerHTML='<option value="0">全部人员</option>';
  }
}

async function confirmRecordsAccess(){
  const input=document.getElementById("recordsAccessPassword");
  const password=input.value;
  if(!password){alert("请输入记录查看密码");input.focus();return;}
  try{
    const response=await fetch(API.recordsVerify,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({records_password:password})});
    const json=await response.json();
    if(!response.ok||json.code!==0){alert(json.detail||"记录查看密码错误");input.select();return;}
    recordsVisible=true;
    recordsSessionPassword=password;
    applyRecordsVisibility();
    closeModal("recordsAccessModal");
    input.value="";
    if(activeTab!=="staff")switchTab("reports");
  }catch(e){alert("验证失败: "+e);}
}

async function confirmAdminToolsAccess(){
  const input=document.getElementById("adminToolsPassword");
  const password=input.value;
  if(!password){alert("\u8bf7\u8f93\u5165\u7ba1\u7406\u5bc6\u7801");input.focus();return;}
  try{
    const r=await fetch(API.adminVerify,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({admin_password:password})});
    const j=await r.json();
    if(!r.ok||j.code!==0){alert(j.detail||"\u7ba1\u7406\u5bc6\u7801\u9519\u8bef");input.select();return;}
    adminToolsVisible=true;
    adminSessionPassword=password;
    applyAdminToolsVisibility();
    closeModal("adminToolsModal");
    input.value="";
  }catch(e){alert("\u9a8c\u8bc1\u5931\u8d25: "+e);}
}







// ---- Init ----



document.addEventListener("DOMContentLoaded", () => {



  setupTabs();



  updateClock(); setInterval(updateClock, 1000);



  document.getElementById("confirmOpen")?.addEventListener("click", confirmOpen);



  document.getElementById("confirmExtend")?.addEventListener("click", confirmExtend);



  document.getElementById("confirmBooking")?.addEventListener("click", confirmBooking);



  document.getElementById("confirmMember")?.addEventListener("click", confirmMember);



  document.getElementById("confirmEditMember")?.addEventListener("click", confirmEditMember);



  document.getElementById("confirmRecharge")?.addEventListener("click", confirmRecharge);
  document.getElementById("confirmRechargeLog")?.addEventListener("click", confirmRechargeLog);
  document.getElementById("confirmBillingHistory")?.addEventListener("click", confirmBillingHistory);



  document.getElementById("confirmResetPwd")?.addEventListener("click", confirmResetPwd);

  document.getElementById("confirmStoreDrink")?.addEventListener("click", confirmStoreDrink);
  document.getElementById("confirmExpiredDrink")?.addEventListener("click", confirmExpiredDrink);



  document.getElementById("confirmPackage")?.addEventListener("click", confirmPackage);






  document.getElementById("confirmDeletePkg")?.addEventListener("click", confirmDeletePkg);



  document.getElementById("confirmInventory")?.addEventListener("click", confirmInventory);

  document.getElementById("confirmStaff")?.addEventListener("click", confirmStaff);

  document.getElementById("confirmAdminTools")?.addEventListener("click", confirmAdminToolsAccess);
  document.getElementById("adminToolsPassword")?.addEventListener("keydown",e=>{if(e.key==="Enter"){e.preventDefault();confirmAdminToolsAccess();}});
  document.getElementById("confirmRecordsAccess")?.addEventListener("click", confirmRecordsAccess);
  document.getElementById("recordsAccessPassword")?.addEventListener("keydown",e=>{if(e.key==="Enter"){e.preventDefault();confirmRecordsAccess();}});



  // Close modals via overlay click or X button



  document.querySelectorAll(".modal-overlay").forEach(ov => {



    ov.addEventListener("click", e => { if (e.target===ov) closeModal(ov.id); });



    const m=ov.querySelector(".modal"); if(m&&!m.querySelector(".modal-close")){



      const x=document.createElement("button"); x.className="modal-close"; x.innerHTML="&times;";



      x.addEventListener("click",()=>closeModal(ov.id)); m.appendChild(x);



    }



  });



  document.getElementById("settlePayment")?.addEventListener("change",function(){



    document.getElementById("memberSettleInfo").style.display=this.value==="会员余额"?"block":"none";



  });



  applyRecordsVisibility();
  switchTab("rooms");



// ---- Ctrl+/ toggle sensitive management fields ----




document.addEventListener("keydown",function(e){
  if(!e.ctrlKey||e.shiftKey||(e.key!=="/"&&e.code!=="Slash")||e.repeat)return;
  e.preventDefault();
  if(adminToolsVisible){adminToolsVisible=false;adminSessionPassword="";applyAdminToolsVisibility();return;}
  const input=document.getElementById("adminToolsPassword");
  input.value="";
  showModal("adminToolsModal");
  setTimeout(()=>input.focus(),0);
});

document.addEventListener("keydown",function(e){
  if(!e.ctrlKey||e.altKey||e.repeat||!["Backslash","IntlBackslash"].includes(e.code))return;
  e.preventDefault();
  if(recordsVisible){
    recordsVisible=false;
    recordsSessionPassword="";
    applyRecordsVisibility();
    if(["reports","recharges","logs","commissions"].includes(activeTab))switchTab("rooms");
    return;
  }
  const input=document.getElementById("recordsAccessPassword");
  input.value="";
  showModal("recordsAccessModal");
  setTimeout(()=>input.focus(),0);
});

});








function updateClock(){document.getElementById("clock").textContent=new Date().toLocaleString("zh-CN",{hour12:false});}



function showModal(id){document.getElementById(id).classList.add("show");}



function closeModal(id){document.getElementById(id).classList.remove("show");}







// ---- Tabs ----



function setupTabs(){document.querySelectorAll(".tab-btn").forEach(b=>b.addEventListener("click",()=>switchTab(b.dataset.tab)));}

function clearPolling(){pollingTimers.forEach(clearInterval);pollingTimers=[];}

function addPolling(fn, interval){pollingTimers.push(setInterval(fn, interval));}

function switchTab(tab){
  if(tab==="commissions"&&!recordsVisible)tab="rooms";
  activeTab=tab;
  document.querySelectorAll(".tab-btn").forEach(b=>b.classList.toggle("active",b.dataset.tab===tab));
  document.querySelectorAll(".tab-panel").forEach(p=>p.classList.toggle("active",p.id==="tab-"+tab));
  clearPolling();

  if(tab==="rooms"){
    fetchRooms();fetchBookings();fetchPowerStatus();
    addPolling(fetchRooms,5000);addPolling(fetchBookings,30000);addPolling(fetchPowerStatus,15000);
  }else if(tab==="members"){
    fetchMembers();addPolling(fetchMembers,10000);
  }else if(tab==="checkout"){
    fetchActiveBilling();fetchInventory();fetchPackages();addPolling(fetchActiveBilling,10000);
  }else if(tab==="reports"){
    initDailyReport();
  }else if(tab==="commissions"){
    const input=document.getElementById("commissionMonth");
    if(!input.value)input.value=_currentBusinessDate().substring(0,7);
    fetchCommissionReport();
  }else if(tab==="packages"){
    fetchPackages();fetchInventory();
  }else if(tab==="inventory"){
    fetchInventory();
  }else if(tab==="staff"){
    fetchStaff();
  }else if(tab==="history"){
    initBillingHistory();
  }else if(tab==="recharges"){
    fetchRechargeLogs();
  }else if(tab==="logs"){
    initOperationLogs();
  }
}


// ================================================================
// Daily Business Report
// ================================================================

function switchCommissionView(view){
  const people=view!=="orders";
  document.getElementById("commissionPeoplePanel").style.display=people?"":"none";
  document.getElementById("commissionOrdersPanel").style.display=people?"none":"";
  ["People","Orders"].forEach(name=>{
    const active=(name==="People")===people,button=document.getElementById("commission"+name+"Tab");
    button.classList.toggle("active",active);button.setAttribute("aria-selected",String(active));
  });
}

function clearCommissionReport(message){
  const performance=document.getElementById("commissionPerformance");
  if(!performance)return;
  performance.textContent="—";
  document.getElementById("commissionConsumption").textContent="—";
  document.getElementById("commissionRecharge").textContent="—";
  document.getElementById("commissionTotal").textContent="—";
  document.getElementById("commissionBillCount").textContent="—";
  document.getElementById("commissionUnassignedHint").textContent="";
  document.getElementById("commissionWarning").style.display="none";
  document.getElementById("commissionWarning").textContent="";
  document.getElementById("commissionRange").textContent="按开台时间统计，营业日早上 6 点切换";
  document.querySelector("#commissionPeopleTable tbody").innerHTML='<tr><td colspan="9" class="empty-hint">'+escapeHtml(message)+'</td></tr>';
  document.querySelector("#commissionOrdersTable tbody").innerHTML='<tr><td colspan="9" class="empty-hint">'+escapeHtml(message)+'</td></tr>';
}

function onCommissionMonthChange(){
  document.getElementById("commissionStaff").value="0";
  fetchCommissionReport();
}

function setCommissionCurrentMonth(){
  document.getElementById("commissionMonth").value=_currentBusinessDate().substring(0,7);
  onCommissionMonthChange();
}

function changeCommissionMonth(offset){
  const input=document.getElementById("commissionMonth"),parts=(input.value||_currentBusinessDate().substring(0,7)).split("-").map(Number);
  const date=new Date(parts[0],parts[1]-1+offset,1);
  input.value=_localDateText(date).substring(0,7);
  onCommissionMonthChange();
}

async function fetchCommissionReport(){
  if(!recordsVisible||!recordsSessionPassword){clearCommissionReport("请先验证记录查看密码");return;}
  const requestId=++commissionRequestId,input=document.getElementById("commissionMonth");
  input.value=input.value||_currentBusinessDate().substring(0,7);
  const staffId=document.getElementById("commissionStaff").value||"0";
  clearCommissionReport("正在加载...");
  try{
    const response=await fetch(API.commissionReport+"?month="+encodeURIComponent(input.value)+"&staff_id="+encodeURIComponent(staffId),{headers:{"X-Records-Password":recordsSessionPassword}}),json=await response.json();
    if(requestId!==commissionRequestId||!recordsVisible)return;
    if(!response.ok||json.code!==0)throw new Error(json.detail||"提成加载失败");
    renderCommissionReport(json.data,staffId);
  }catch(e){
    if(requestId===commissionRequestId&&recordsVisible)clearCommissionReport("提成加载失败："+e.message);
  }
}

function commissionTierHtml(person,key){
  const rule=person.rule||{},marketing=rule.type==="marketing";
  if((key==="fixed"&&rule.type!=="manager")||(key!=="fixed"&&!marketing))return "—";
  let range="全部业绩";
  if(key==="first")range="前 "+rule.first_limit+" 元部分";
  if(key==="second")range="超过 "+rule.first_limit+" 至 "+rule.second_limit+" 元部分";
  if(key==="third")range="超过 "+rule.second_limit+" 元部分";
  return '<strong>'+_reportMoney(person[key+"_commission"])+'</strong><div class="cell-note">'+escapeHtml(range)+'</div><div class="cell-note">'+_reportMoney(person[key+"_amount"])+" × "+Number(rule[key+"_rate"])+"%</div>";
}

function renderCommissionReport(report,selectedStaff="0"){
  const summary=report.summary||{};
  document.getElementById("commissionPerformance").textContent=_reportMoney(summary.performance_total);
  document.getElementById("commissionConsumption").textContent=_reportMoney(summary.consumption_total);
  document.getElementById("commissionRecharge").textContent=_reportMoney(summary.recharge_total);
  document.getElementById("commissionTotal").textContent=_reportMoney(summary.commission_total);
  document.getElementById("commissionBillCount").textContent=Number(summary.bill_count||0)+" 条";
  document.getElementById("commissionRange").textContent="统计范围："+report.start_at+" 至 "+report.end_at+"（不含结束时间）";
  const select=document.getElementById("commissionStaff");
  select.innerHTML='<option value="0">全部人员</option>'+(report.staff_options||[]).map(person=>'<option value="'+Number(person.id)+'">'+escapeHtml(person.name)+(person.status!=="在职"?"（"+escapeHtml(person.status)+"）":"")+'</option>').join("");
  select.value=selectedStaff;
  document.getElementById("commissionUnassignedHint").textContent="本月全店另有 "+Number(report.unassigned_count||0)+" 条符合渠道条件、但选择无或未归属的业绩记录，不计入提成；可在结账记录或充卡记录的隐藏编辑功能中补选人员。";
  const people=report.people||[],warning=document.getElementById("commissionWarning"),changed=people.filter(person=>person.rule_changed);
  warning.style.display=changed.length?"":"none";
  warning.textContent=changed.length?"请核对："+changed.map(person=>person.name+"："+(person.warning||"历史规则有变化")).join("；"):"";
  document.querySelector("#commissionPeopleTable tbody").innerHTML=people.length?people.map(person=>
    '<tr><td>'+escapeHtml(person.name)+(person.status!=="在职"?'<div class="cell-note">'+escapeHtml(person.status)+'</div>':'')+'</td><td title="'+escapeHtml(staffCommissionText(person.rule))+'">'+escapeHtml(person.rule.type==="marketing"?"营销 · 阶梯分段":person.rule.type==="manager"?"经理 · 固定比例":"不计算")+'<div class="cell-note">'+escapeHtml(person.rule_source)+(person.rule_changed?' · 规则有变化':'')+'</div></td><td>'+_reportMoney(person.performance_total)+'<div class="cell-note">消费 '+_reportMoney(person.consumption_total)+' / 充卡 '+_reportMoney(person.recharge_total)+'</div></td><td>'+Number(person.bill_count||0)+'</td><td>'+commissionTierHtml(person,"first")+'</td><td>'+commissionTierHtml(person,"second")+'</td><td>'+commissionTierHtml(person,"third")+'</td><td>'+commissionTierHtml(person,"fixed")+'</td><td class="report-total-cell">'+_reportMoney(person.commission_total)+'</td></tr>'
  ).join(""):'<tr><td colspan="9" class="empty-hint">暂无营销或经理业绩，先在人员管理配置提成类型，并在结账或充值时选择归属人员</td></tr>';
  const orders=report.orders||[];
  document.querySelector("#commissionOrdersTable tbody").innerHTML=orders.length?orders.map(order=>
    '<tr><td>'+escapeHtml(order.source)+'</td><td>'+escapeHtml(order.record_id)+'</td><td>'+escapeHtml(order.source==="消费"?(order.room_no||"-"):(order.member_name||"-"))+'</td><td class="cell-time">'+escapeHtml(order.occurred_at||"-")+'</td><td>'+escapeHtml(order.staff_name||"-")+'</td><td>'+_reportMoney(order.original_amount)+(order.source==="充卡"&&Number(order.gift_amount||0)>0?'<div class="cell-note">另赠 '+_reportMoney(order.gift_amount)+'</div>':'')+'</td><td class="report-total-cell">'+_reportMoney(order.performance_amount)+'</td><td>'+escapeHtml(order.payment_method||"-")+'</td><td>'+escapeHtml(order.notes||"-")+'</td></tr>'
  ).join(""):'<tr><td colspan="9" class="empty-hint">该月份暂无关联的业绩记录</td></tr>';
}

function _localDateText(date){
  const year=date.getFullYear();
  const month=String(date.getMonth()+1).padStart(2,"0");
  const day=String(date.getDate()).padStart(2,"0");
  return year+"-"+month+"-"+day;
}

function _currentBusinessDate(){
  const now=new Date();
  if(now.getHours()<6)now.setDate(now.getDate()-1);
  return _localDateText(now);
}

function initDailyReport(){
  const input=document.getElementById("reportDate");
  if(!input.value)input.value=_currentBusinessDate();
  const month=document.getElementById("reportMonth");
  if(!month.value)month.value=input.value.substring(0,7);
  switchReportView(currentReportView);
}

function switchReportView(view){
  currentReportView=view==="monthly"?"monthly":"daily";
  const daily=currentReportView==="daily";
  document.getElementById("dailyReportPanel").style.display=daily?"":"none";
  document.getElementById("monthlyReportPanel").style.display=daily?"none":"";
  const dailyTab=document.getElementById("dailyReportTab");
  const monthlyTab=document.getElementById("monthlyReportTab");
  dailyTab.classList.toggle("active",daily);
  monthlyTab.classList.toggle("active",!daily);
  dailyTab.setAttribute("aria-selected",daily?"true":"false");
  monthlyTab.setAttribute("aria-selected",daily?"false":"true");
  if(daily)fetchDailyReport();else fetchMonthlyReport();
}

function setReportToday(){
  document.getElementById("reportDate").value=_currentBusinessDate();
  fetchDailyReport();
}

function changeReportDate(offset){
  const input=document.getElementById("reportDate");
  const parts=(input.value||_currentBusinessDate()).split("-").map(Number);
  const date=new Date(parts[0],parts[1]-1,parts[2]);
  date.setDate(date.getDate()+offset);
  input.value=_localDateText(date);
  fetchDailyReport();
}

function _reportMoney(value){return "¥"+Number(value||0).toFixed(2);}

async function fetchDailyReport(){
  const date=document.getElementById("reportDate").value||_currentBusinessDate();
  document.getElementById("reportDate").value=date;
  const tbody=document.querySelector("#dailyReportTable tbody");
  tbody.innerHTML='<tr><td colspan="10" class="empty-hint">正在加载...</td></tr>';
  try{
    const response=await fetch(API.dailyReport+"?date="+encodeURIComponent(date),{headers:{"X-Records-Password":recordsSessionPassword}});
    const json=await response.json();
    if(!response.ok||json.code!==0)throw new Error(json.detail||"报表加载失败");
    renderDailyReport(json.data);
  }catch(e){
    tbody.innerHTML='<tr><td colspan="10" class="empty-hint">报表加载失败：'+escapeHtml(e.message)+'</td></tr>';
  }
}

function renderDailyReport(report){
  const summary=report.summary||{};
  document.getElementById("reportActualIncomeTotal").textContent=_reportMoney(summary.actual_income_total);
  document.getElementById("reportBusinessTotal").textContent=_reportMoney(summary.business_total);
  document.getElementById("reportCheckoutReceivedTotal").textContent=_reportMoney(summary.checkout_received_total);
  document.getElementById("reportRechargeTotal").textContent=_reportMoney(summary.recharge_total);
  document.getElementById("reportMemberPayTotal").textContent=_reportMoney(summary.member_balance_total);
  document.getElementById("reportBillCount").textContent=Number(summary.bill_count||0)+" 单";
  document.getElementById("reportRange").textContent="统计范围："+report.start_at+" 至 "+report.end_at+"（不含结束时间）";

  const payments=report.payment_breakdown||[];
  document.getElementById("reportPaymentSummary").innerHTML=payments.map(item=>
    '<div class="payment-summary-item"><span>'+escapeHtml(item.method)+'</span><strong>'+_reportMoney(item.amount)+'</strong></div>'
  ).join("");

  const bills=report.bills||[];
  document.getElementById("reportBillHint").textContent="共 "+bills.length+" 条";
  const tbody=document.querySelector("#dailyReportTable tbody");
  if(!bills.length){tbody.innerHTML='<tr><td colspan="10" class="empty-hint">该营业日暂无结账记录</td></tr>';return;}
  tbody.innerHTML=bills.map(bill=>{
    const member=bill.settlement_member_name
      ? escapeHtml(bill.settlement_member_name)+'<div class="cell-note">'+escapeHtml(bill.settlement_member_phone||"")+'</div>'
      : "-";
    const openTime=bill.open_at?String(bill.open_at).replace("T"," ").substring(0,19):(bill.close_at?String(bill.close_at).replace("T"," ").substring(0,19):"-");
    const closeTime=bill.close_at?String(bill.close_at).replace("T"," ").substring(0,19):"-";
    return '<tr><td class="cell-time">'+openTime+'</td><td class="cell-time">'+closeTime+'</td><td>'+escapeHtml(bill.room_no||"-")+'</td><td>'+escapeHtml(bill.package_name||"-")+'</td><td>'+_reportMoney(bill.room_fee)+'</td><td>'+_reportMoney(bill.drinks_fee)+'</td><td class="report-total-cell">'+_reportMoney(bill.total)+'</td><td>'+billingPaymentHtml(bill)+'</td><td>'+member+'</td><td>'+escapeHtml(bill.notes||"-")+'</td></tr>';
  }).join("");
}

function setReportCurrentMonth(){
  document.getElementById("reportMonth").value=_currentBusinessDate().substring(0,7);
  fetchMonthlyReport();
}

function changeReportMonth(offset){
  const input=document.getElementById("reportMonth");
  const parts=(input.value||_currentBusinessDate().substring(0,7)).split("-").map(Number);
  const date=new Date(parts[0],parts[1]-1+offset,1);
  input.value=String(date.getFullYear())+"-"+String(date.getMonth()+1).padStart(2,"0");
  fetchMonthlyReport();
}

async function fetchMonthlyReport(){
  const input=document.getElementById("reportMonth");
  const month=input.value||_currentBusinessDate().substring(0,7);
  input.value=month;
  const tbody=document.querySelector("#monthlyReportTable tbody");
  tbody.innerHTML='<tr><td colspan="10" class="empty-hint">正在加载...</td></tr>';
  try{
    const response=await fetch(API.monthlyReport+"?month="+encodeURIComponent(month),{headers:{"X-Records-Password":recordsSessionPassword}});
    const json=await response.json();
    if(!response.ok||json.code!==0)throw new Error(json.detail||"月报加载失败");
    renderMonthlyReport(json.data);
  }catch(e){
    tbody.innerHTML='<tr><td colspan="10" class="empty-hint">月报加载失败：'+escapeHtml(e.message)+'</td></tr>';
  }
}

function renderMonthlyReport(report){
  const summary=report.summary||{};
  document.getElementById("monthlyActualIncome").textContent=_reportMoney(summary.actual_income_total);
  document.getElementById("monthlyMeituan").textContent=_reportMoney(summary["美团"]);
  document.getElementById("monthlyWechat").textContent=_reportMoney(summary["微信"]);
  document.getElementById("monthlyAlipay").textContent=_reportMoney(summary["支付宝"]);
  document.getElementById("monthlyCash").textContent=_reportMoney(summary["现金"]);
  document.getElementById("monthlyOther").textContent=_reportMoney(summary["其他"]);
  document.getElementById("monthlyRecharge").textContent=_reportMoney(summary.recharge_total);
  document.getElementById("monthlyMemberBalance").textContent=_reportMoney(summary.member_balance_total);
  document.getElementById("monthlyBillCount").textContent=Number(summary.bill_count||0)+" 单";
  document.getElementById("monthlyReportRange").textContent="统计范围："+report.start_at+" 至 "+report.end_at+"（不含结束时间）";

  const days=report.days||[];
  const tbody=document.querySelector("#monthlyReportTable tbody");
  if(!days.length){tbody.innerHTML='<tr><td colspan="10" class="empty-hint">该月暂无数据</td></tr>';return;}
  tbody.innerHTML=days.map(day=>
    '<tr class="monthly-day-row" data-report-date="'+escapeHtml(day.business_date)+'" title="查看当日营业日报">'+
    '<td>'+escapeHtml(day.business_date)+'</td>'+
    '<td class="report-total-cell">'+_reportMoney(day.actual_income_total)+'</td>'+
    '<td>'+_reportMoney(day["美团"])+'</td><td>'+_reportMoney(day["微信"])+'</td>'+
    '<td>'+_reportMoney(day["支付宝"])+'</td><td>'+_reportMoney(day["现金"])+'</td>'+
    '<td>'+_reportMoney(day["其他"])+'</td><td>'+_reportMoney(day.recharge_total)+'</td>'+
    '<td>'+_reportMoney(day.member_balance_total)+'</td><td>'+Number(day.bill_count||0)+' 单</td></tr>'
  ).join("");
  tbody.querySelectorAll(".monthly-day-row").forEach(row=>{
    row.addEventListener("click",()=>openDailyReportFromMonth(row.dataset.reportDate));
  });
}

function openDailyReportFromMonth(date){
  document.getElementById("reportDate").value=date;
  switchReportView("daily");
  document.getElementById("tab-reports").scrollIntoView({behavior:"smooth",block:"start"});
}
// Room Management



// ================================================================







async function fetchRooms(){
  const notice=document.getElementById("roomsNotice");
  try{
    const r=await fetch(API.rooms),j=await r.json();
    if(!r.ok||j.code!==0)throw new Error(j.detail||j.msg||"房间接口异常");
    roomsData=j.data||[];
    renderRooms();
    if(j.source==="cache"){
      notice.textContent=j.warning||"设备服务器暂时无法连接，当前显示缓存房间。";
      notice.style.display="block";
      document.getElementById("serverStatus").classList.add("offline");
    }else{
      notice.style.display="none";
      document.getElementById("serverStatus").classList.remove("offline");
    }
  }catch(e){
    document.getElementById("serverStatus").classList.add("offline");
    notice.textContent="房间数据加载失败："+e.message;
    notice.style.display="block";
    if(!roomsData.length)document.getElementById("roomsGrid").innerHTML='<div class="empty-hint room-load-error">暂无可显示房间，请检查设备服务器或房间缓存。</div>';
  }
}







async function fetchPowerStatus(){try{const r=await fetch(API.roomStatus);const j=await r.json();if(j.code===0)renderPowerStrip(j.data);}catch(e){}}







function renderPowerStrip(data){



  const s=document.getElementById("powerStrip"),ps=new Set((data||[]).map(d=>d.ip));



  const items=roomsData.map(r=>{const on=ps.has(r.room_ip);return '<span class="'+(on?"ps-item":"ps-item offline")+'">'+r.room_no+" "+(on?"已通电":"未通电")+'</span>';});



  s.innerHTML=items.length?'<span class="ps-label">房间通电状态</span>'+items.join(""):'<span style="color:var(--text-dim);font-size:13px;">房间通电状态：暂无数据</span>';



}







function renderRooms(){



  const g=document.getElementById("roomsGrid");

  if(!roomsData.length){g.innerHTML='<div class="empty-hint room-load-error">暂无房间数据</div>';return;}



  g.innerHTML=roomsData.map(r=>{



    const sc=r.powered_on?"state-"+r.room_state:"offline";



    const bc=!r.powered_on?"badge-offline":r.room_state===1?"badge-active":"badge-idle";



    const bt=!r.powered_on?"未通电":r.room_state===1?"已开台":"空闲";



    let th="";if(r.room_state===1&&r.auto_close_at)th='<div class="room-timer" id="timer-'+r.room_no+'">--:--:--</div>';else if(r.room_state===1)th='<div class="room-timer">开台中</div>';



    let info=r.powered_on?"IP: "+r.room_ip+" | MAC: "+r.room_mac:"房间未通电";



    let act="";if(!r.powered_on)act=r.room_state===1?'<button class="btn btn-danger" onclick="deviceCloseRoom(\''+r.room_no+'\')">关台</button>':'<span style="color:var(--text-dim);font-size:13px;">房间未通电</span>';



    else if(r.room_state===0)act='<button class="btn btn-primary" onclick="openRoom(\''+r.room_no+'\')">开台</button>';



    else act='<button class="btn btn-outline" onclick="extendRoom(\''+r.room_no+'\')">续时</button><button class="btn btn-danger" onclick="closeRoom(\''+r.room_no+'\')">关台</button>';



    return '<div class="room-card '+sc+'"><div class="room-header"><span class="room-no">'+r.room_no+'</span><span class="room-badge '+bc+'">'+bt+'</span></div><div class="room-info">'+info+'</div>'+th+'<div class="room-actions">'+act+'</div></div>';



  }).join("");



  updateAllCountdowns();



}







function updateAllCountdowns(){roomsData.forEach(r=>{if(r.room_state===1&&r.auto_close_at)startCountdown("timer-"+r.room_no,r.auto_close_at);});}







function startCountdown(eid,closeAt){



  if(countdownTimers[eid])clearInterval(countdownTimers[eid]);



  const el=document.getElementById(eid);if(!el)return;



  const tick=()=>{const d=new Date(closeAt)-new Date();if(d<=0){el.textContent="00:00:00";el.classList.add("countdown-warning");if(countdownTimers[eid])clearInterval(countdownTimers[eid]);return;}el.textContent=String(Math.floor(d/3600000)).padStart(2,"0")+":"+String(Math.floor((d%3600000)/60000)).padStart(2,"0")+":"+String(Math.floor((d%60000)/1000)).padStart(2,"0");el.classList.toggle("countdown-warning",d<300000);};



  tick();countdownTimers[eid]=setInterval(tick,1000);



}







// ---- Duration helpers ----



function onOpenDurationChange(){document.getElementById("openCustomDur").style.display=document.getElementById("openDuration").value==="custom"?"flex":"none";}



function onExtendDurationChange(){document.getElementById("extendCustomDur").style.display=document.getElementById("extendDuration").value==="custom"?"flex":"none";}



function onBookingDurationChange(){document.getElementById("bookingCustomDur").style.display=document.getElementById("bookingDuration").value==="custom"?"flex":"none";}



function getDuration(selId,hId,mId){const v=document.getElementById(selId).value;if(v==="unlimited")return{type:"unlimited",min:null};if(v==="custom"){const h=parseInt(document.getElementById(hId).value)||0,m=parseInt(document.getElementById(mId).value)||0,t=h*60+m;if(t<1)return null;return{type:"timed",min:t};}return{type:"timed",min:parseInt(v)};}







// ---- Open Room ----



async function openRoom(roomNo){



  currentRoom=roomsData.find(r=>r.room_no===roomNo);if(!currentRoom)return;



  if(!(await checkRoomBillable(roomNo)))return;



  document.getElementById("openRoomLabel").textContent=roomNo;



  document.getElementById("openDuration").value="180";onOpenDurationChange();



  showModal("openModal");



}







async function confirmOpen(){



  if(!currentRoom)return;



  const dur=getDuration("openDuration","openHours","openMins");if(!dur)return;



  const body={room_ip:currentRoom.room_ip,room_name:currentRoom.room_no,duration_type:dur.type,duration_minutes:dur.min,customer_type:"retail"};



  try{
    const r=await fetch(API.open,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}),j=await r.json();
    if(j.code===0){closeModal("openModal");fetchRooms();}
    else if(r.status===409){closeModal("openModal");alert(j.detail||"该房间有待结账账单，请先结账");switchTab("checkout");}
    else alert("开台失败："+(j.detail||j.msg||"unknown"));
  }



  catch(e){alert("请求失败: "+e);}



}







// ---- Close ----



async function closeRoom(roomNo){



  const room=roomsData.find(r=>r.room_no===roomNo);if(!room)return;



  if(!confirm("确认关台 "+roomNo+"？"))return;



  try{
    const r=await fetch(API.close,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({room_ip:room.room_ip,room_name:room.room_no})}),j=await r.json();
    if(j.code===0){alert("关台成功，账单已转到收银台，请完成结账。");switchTab("checkout");}
    else alert("关台失败: "+(j.detail||j.msg||"unknown"));
  }



  catch(e){alert("请求失败: "+e);}



}



async function deviceCloseRoom(roomNo){
  const room=roomsData.find(r=>r.room_no===roomNo);if(!room)return;
  if(!confirm("确认调用设备接口关台 "+roomNo+"？"))return;
  try{
    const r=await fetch(API.deviceClose,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({room_ip:room.room_ip,room_name:room.room_no})}),j=await r.json();
    if(r.ok&&j.code===0){alert("设备关台指令调用成功");fetchRooms();fetchPowerStatus();}
    else alert("设备关台失败: "+(j.detail||j.msg||"unknown"));
  }catch(e){alert("请求失败: "+e);}
}







// ---- Extend ----



function extendRoom(roomNo){



  currentRoom=roomsData.find(r=>r.room_no===roomNo);if(!currentRoom)return;



  document.getElementById("extendRoomLabel").textContent=roomNo;



  document.getElementById("extendDuration").value="60";onExtendDurationChange();



  showModal("extendModal");



}







async function confirmExtend(){



  if(!currentRoom)return;



  const dur=getDuration("extendDuration","extendHours","extendMins");if(!dur||!dur.min)return;



  try{const r=await fetch(API.extend,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({room_ip:currentRoom.room_ip,room_name:currentRoom.room_no,duration_minutes:dur.min})});const j=await r.json();if(j.code===0){closeModal("extendModal");fetchRooms();}else alert("续时失败: "+(j.detail||j.msg||"unknown"));}



  catch(e){alert("请求失败: "+e);}



}







// ---- Bookings ----



async function fetchBookings(){try{const r=await fetch(API.bookings);const j=await r.json();if(j.code===0)renderBookings(j.data);}catch(e){}}



function renderBookings(bookings){const l=document.getElementById("bookingsList"),p=bookings.filter(b=>b.status==="pending");if(!p.length){l.innerHTML='<p class="empty-hint">暂无预订</p>';return;}l.innerHTML=p.map(b=>{const t=new Date(b.open_at);return '<div class="booking-item"><span class="booking-room">'+b.room_name+'</span><span class="booking-time">'+t.toLocaleString("zh-CN",{hour12:false})+'</span><button class="booking-cancel" onclick="cancelBooking(\''+b.id+'\')" title="取消">x</button></div>';}).join("");}



function showBookingModal(){const s=document.getElementById("bookingRoom");s.innerHTML=roomsData.map(r=>'<option value="'+r.room_no+'" data-ip="'+r.room_ip+'">'+r.room_no+'</option>').join("");const t=new Date(Date.now()+3600000);t.setMinutes(Math.ceil(t.getMinutes()/5)*5,0,0);document.getElementById("bookingTime").value=t.getFullYear()+"-"+String(t.getMonth()+1).padStart(2,"0")+"-"+String(t.getDate()).padStart(2,"0")+"T"+String(t.getHours()).padStart(2,"0")+":"+String(t.getMinutes()).padStart(2,"0");document.getElementById("bookingDuration").value="120";onBookingDurationChange();showModal("bookingModal");}



async function confirmBooking(){const s=document.getElementById("bookingRoom"),roomNo=s.value,roomIp=s.selectedOptions[0].dataset.ip,openAt=document.getElementById("bookingTime").value;const dur=getDuration("bookingDuration","bookingHours","bookingMins");if(!openAt||!dur)return;try{const r=await fetch(API.bookings,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({room_ip:roomIp,room_name:roomNo,open_at:new Date(openAt).toISOString(),duration_type:dur.type,duration_minutes:dur.min,customer_type:"retail"})});const j=await r.json();if(j.code===0){closeModal("bookingModal");fetchBookings();}else alert("预订失败: "+(j.detail||j.msg||"unknown"));}catch(e){alert("请求失败: "+e);}}



async function cancelBooking(id){if(!confirm("确认取消预订？"))return;try{await fetch(API.bookings+"/"+id,{method:"DELETE"});fetchBookings();}catch(e){alert("取消失败: "+e);}}







// ================================================================



// Member Management (unchanged)



// ================================================================







async function fetchMembers(){try{const r=await fetch(API.members);const j=await r.json();if(j.code===0){membersData=j.data;renderMembers();}}catch(e){}}



function renderMembers(){
  const tb=document.querySelector("#membersTable tbody");
  if(!membersData.length){tb.innerHTML='<tr><td colspan="6" class="empty-hint">暂无会员数据</td></tr>';return;}
  tb.innerHTML=membersData.map(m=>{
    const cr=m.created_at?m.created_at.replace("T"," ").substring(0,19):"-";
    return '<tr><td>'+escapeHtml(m.name)+'</td><td>'+escapeHtml(m.phone)+'</td><td>'+escapeHtml(m.remark||"-")+'</td><td>'+Number(m.balance||0).toFixed(2)+'</td><td style="font-size:12px;color:var(--text-dim);">'+cr+'</td><td><button class="btn btn-xs btn-accent" onclick="showRechargeModal('+m.id+')">充值</button> <button class="btn btn-xs btn-outline" onclick="showStoredDrinksModal('+m.id+')">存酒</button> <button class="btn btn-xs btn-outline" onclick="showEditMemberModal('+m.id+')">编辑</button> <button class="btn btn-xs btn-secondary" onclick="showResetPwdModal('+m.id+')">重置密码</button></td></tr>';
  }).join("");
}
function escapeHtml(value){return String(value??"").replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[ch]));}

async function showStoredDrinksModal(memberId){
  const member=membersData.find(item=>item.id===memberId);if(!member)return;
  currentStoredDrinkMember=member;
  document.getElementById("storedDrinksMemberLabel").textContent=member.name+"（"+member.phone+"）";
  document.getElementById("storedDrinkName").value="";
  document.getElementById("storedDrinkKind").value="sealed";
  document.getElementById("storedDrinkQty").value="1";
  document.getElementById("storedDrinkLocation").value="";
  document.getElementById("storedDrinkNotes").value="";
  onStoredDrinkKindChange();
  showModal("storedDrinksModal");
  fetchStoredDrinkOptions();
  await fetchMemberStoredDrinks();
}

async function fetchStoredDrinkOptions(){
  try{
    const r=await fetch(API.inventory),j=await r.json();
    if(j.code!==0)return;
    const names=[...new Set(j.data.filter(item=>item.category==="酒水").map(item=>item.name))];
    document.getElementById("storedDrinkOptions").innerHTML=names.map(name=>'<option value="'+escapeHtml(name)+'"></option>').join("");
  }catch(e){}
}

function onStoredDrinkKindChange(){
  const opened=document.getElementById("storedDrinkKind").value==="opened";
  const qty=document.getElementById("storedDrinkQty");
  document.getElementById("storedDrinkLevelGroup").style.display=opened?"block":"none";
  qty.disabled=opened;
  if(opened)qty.value="1";
}

async function fetchMemberStoredDrinks(){
  if(!currentStoredDrinkMember)return;
  try{
    const r=await fetch(API.members+"/"+currentStoredDrinkMember.id+"/stored-drinks"),j=await r.json();
    if(!r.ok||j.code!==0){alert("读取存酒失败: "+(j.detail||"unknown"));return;}
    memberStoredDrinksData=j.data||[];
    renderMemberStoredDrinks(memberStoredDrinksData,j.logs||[]);
  }catch(e){alert("读取存酒失败: "+e);}
}

function renderMemberStoredDrinks(records,logs){
  const tb=document.querySelector("#storedDrinksTable tbody");
  if(!records.length)tb.innerHTML='<tr><td colspan="6" class="empty-hint">暂无存酒</td></tr>';
  else tb.innerHTML=records.map(item=>{
    const opened=item.storage_kind==="opened";
    const amount=opened?("已开封 · 剩余 "+escapeHtml(item.remaining_level||"未记录")):(item.quantity+" 瓶（未开封）");
    const expiry=item.is_expired?'<span class="storage-expiry expired">已过期</span>':'<span class="storage-expiry">剩 '+item.days_remaining+' 天</span>';
    const expireDisabled=item.is_expired?'':' disabled title="存酒尚未过期"';
    return '<tr class="'+(item.is_expired?'stored-drink-expired':'')+'"><td><strong>'+escapeHtml(item.item_name)+'</strong>'+(item.notes?'<div class="cell-note">'+escapeHtml(item.notes)+'</div>':'')+'</td><td>'+amount+'</td><td>'+escapeHtml(item.storage_location||"-")+'</td><td class="cell-time">'+escapeHtml((item.stored_at||"").substring(0,16))+'</td><td class="cell-time">'+escapeHtml((item.expires_at||"").substring(0,16))+'<br>'+expiry+'</td><td><button class="btn btn-xs btn-outline" onclick="retrieveStoredDrink('+item.id+')">取酒</button> <button class="btn btn-xs btn-accent" onclick="showExpiredDrinkModal('+item.id+')"'+expireDisabled+'>过期处理</button></td></tr>';
  }).join("");
  const storeButton=document.getElementById("confirmStoreDrink");
  const hasExpired=records.some(item=>item.is_expired);
  storeButton.disabled=hasExpired;
  storeButton.title=hasExpired?"该会员有过期存酒，请先处理后再新增存酒":"";
  const ltb=document.querySelector("#storedDrinkLogsTable tbody");
  if(!logs.length)ltb.innerHTML='<tr><td colspan="6" class="empty-hint">暂无记录</td></tr>';
  else ltb.innerHTML=logs.map(log=>{
    const actionLabels={store:"存酒",retrieve:"取酒",expire_to_inventory:"过期转库存",expire_extend:"过期延期"};
    const action=actionLabels[log.action]||log.action;
    const kind=log.storage_kind==="opened"?("（已开封 "+escapeHtml(log.remaining_level||"")+'）'):"";
    return '<tr><td class="cell-time">'+escapeHtml((log.created_at||"").substring(0,16))+'</td><td>'+action+'</td><td>'+escapeHtml(log.item_name)+kind+'</td><td>'+log.quantity+' 瓶</td><td>'+log.before_quantity+' → '+log.after_quantity+'</td><td>'+escapeHtml(log.detail||"-")+'</td></tr>';
  }).join("");
}

async function confirmStoreDrink(){
  if(!currentStoredDrinkMember)return;
  const kind=document.getElementById("storedDrinkKind").value;
  const data={
    item_name:document.getElementById("storedDrinkName").value.trim(),
    storage_kind:kind,
    quantity:kind==="opened"?1:parseInt(document.getElementById("storedDrinkQty").value,10),
    remaining_level:kind==="opened"?document.getElementById("storedDrinkLevel").value:null,
    storage_location:document.getElementById("storedDrinkLocation").value.trim()||null,
    notes:document.getElementById("storedDrinkNotes").value.trim()||null
  };
  if(!data.item_name){alert("请填写酒水名称");return;}
  if(!Number.isInteger(data.quantity)||data.quantity<1){alert("请输入有效数量");return;}
  if(!confirm("确认给 "+currentStoredDrinkMember.name+" 登记存酒？\n"+data.item_name+"，"+(kind==="opened"?("已开封，剩余 "+data.remaining_level):(data.quantity+" 瓶未开封"))+"\n有效期 30 天"))return;
  try{
    const r=await fetch(API.members+"/"+currentStoredDrinkMember.id+"/stored-drinks",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)}),j=await r.json();
    if(!r.ok||j.code!==0){alert("存酒失败: "+(j.detail||"unknown"));return;}
    document.getElementById("storedDrinkName").value="";
    document.getElementById("storedDrinkQty").value="1";
    document.getElementById("storedDrinkNotes").value="";
    await fetchMemberStoredDrinks();
  }catch(e){alert("存酒失败: "+e);}
}

async function retrieveStoredDrink(storageId){
  if(!currentStoredDrinkMember)return;
  const item=memberStoredDrinksData.find(record=>record.id===storageId);if(!item)return;
  let quantity=1;
  if(item.storage_kind==="sealed"){
    const input=prompt("取出多少瓶？当前剩余 "+item.quantity+" 瓶","1");
    if(input===null)return;
    quantity=parseInt(input,10);
    if(!Number.isInteger(quantity)||quantity<1||quantity>item.quantity){alert("请输入 1 到 "+item.quantity+" 之间的整数");return;}
  }
  const expiryWarning=item.is_expired?"\n注意：这批存酒已过期。":"";
  if(!confirm("确认取酒："+item.item_name+"，数量 "+quantity+" 瓶？"+expiryWarning))return;
  try{
    const r=await fetch(API.members+"/"+currentStoredDrinkMember.id+"/stored-drinks/"+storageId+"/retrieve",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({quantity})}),j=await r.json();
    if(!r.ok||j.code!==0){alert("取酒失败: "+(j.detail||"unknown"));return;}
    await fetchMemberStoredDrinks();
  }catch(e){alert("取酒失败: "+e);}
}

async function showExpiredDrinkModal(storageId){
  if(!currentStoredDrinkMember)return;
  const item=memberStoredDrinksData.find(record=>record.id===storageId);
  if(!item)return;
  if(!item.is_expired){alert("存酒尚未过期，不能进行过期处理");return;}
  currentExpiredDrinkId=storageId;
  document.getElementById("expiredDrinkLabel").textContent=item.item_name;
  document.getElementById("expiredDrinkSummary").textContent=
    currentStoredDrinkMember.name+" · "+item.quantity+" 瓶 · 到期时间 "+String(item.expires_at||"").substring(0,16);
  document.getElementById("expiredDrinkAction").value="inventory";
  document.getElementById("expiredDrinkExtendDays").value="30";
  try{
    const r=await fetch(API.inventory),j=await r.json();
    if(!r.ok||j.code!==0)throw new Error(j.detail||"库存读取失败");
    const inventories=(j.data||[]).filter(x=>x.category==="酒水").sort((a,b)=>{
      if(a.name===item.item_name&&b.name!==item.item_name)return -1;
      if(b.name===item.item_name&&a.name!==item.item_name)return 1;
      return String(a.name).localeCompare(String(b.name),"zh-CN");
    });
    document.getElementById("expiredDrinkInventory").innerHTML=inventories.length
      ?inventories.map(x=>'<option value="'+x.id+'">'+escapeHtml(x.name)+'（当前 '+Number(x.stock||0)+' 瓶）</option>').join("")
      :'<option value="">暂无酒水库存商品</option>';
    onExpiredDrinkActionChange();
    showModal("expiredDrinkModal");
  }catch(e){alert("打开过期处理失败: "+e.message);}
}


function onExpiredDrinkActionChange(){
  const action=document.getElementById("expiredDrinkAction").value;
  document.getElementById("expiredDrinkInventoryGroup").style.display=action==="inventory"?"block":"none";
  document.getElementById("expiredDrinkExtendGroup").style.display=action==="extend"?"block":"none";
}


async function confirmExpiredDrink(){
  if(!currentStoredDrinkMember||!currentExpiredDrinkId)return;
  const action=document.getElementById("expiredDrinkAction").value;
  const data={action};
  if(action==="inventory"){
    data.inventory_id=parseInt(document.getElementById("expiredDrinkInventory").value,10);
    if(!data.inventory_id){alert("请先在库存管理添加酒水商品，或选择延长有效期");return;}
  }else{
    data.extend_days=parseInt(document.getElementById("expiredDrinkExtendDays").value,10);
    if(!Number.isInteger(data.extend_days)||data.extend_days<1||data.extend_days>365){alert("延长天数请输入 1 到 365");return;}
  }
  const item=memberStoredDrinksData.find(record=>record.id===currentExpiredDrinkId);
  const message=action==="inventory"
    ?"确认把 "+item.item_name+" "+item.quantity+" 瓶转入所选库存？"
    :"确认从今天起延长 "+data.extend_days+" 天？";
  if(!confirm(message))return;
  try{
    const url=API.members+"/"+currentStoredDrinkMember.id+"/stored-drinks/"+currentExpiredDrinkId+"/expire";
    const r=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)}),j=await r.json();
    if(!r.ok||j.code!==0){alert("过期处理失败: "+(j.detail||j.msg||"unknown"));return;}
    closeModal("expiredDrinkModal");
    currentExpiredDrinkId=null;
    await fetchMemberStoredDrinks();
    if(action==="inventory")await fetchInventory();
    alert(j.msg||"处理成功");
  }catch(e){alert("过期处理失败: "+e);}
}


function showMemberModal(){
  document.getElementById("memberName").value="";
  document.getElementById("memberPhone").value="";
  document.getElementById("memberRemark").value="";
  showModal("memberModal");
}

async function confirmMember(){
  const name=document.getElementById("memberName").value.trim(),phone=document.getElementById("memberPhone").value.trim(),remark=document.getElementById("memberRemark").value.trim()||null;
  if(!name||!phone){alert("请填写姓名和手机号");return;}
  try{
    const r=await fetch(API.members,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name,phone,remark})}),j=await r.json();
    if(r.ok&&j.code===0){closeModal("memberModal");fetchMembers();}else alert("添加失败: "+(j.detail||j.msg||"unknown"));
  }catch(e){alert("请求失败: "+e);}
}
function showEditMemberModal(memberId){
  const m=membersData.find(x=>x.id===memberId);if(!m)return;
  currentMember=m;
  document.getElementById("editMemberLabel").textContent=m.name;
  document.getElementById("editMemberName").value=m.name;
  document.getElementById("editMemberPhone").value=m.phone;
  document.getElementById("editMemberRemark").value=m.remark||"";
  document.getElementById("editMemberBalance").value=Number(m.balance||0).toFixed(2);
  showModal("editMemberModal");
  applyAdminToolsVisibility();
}



async function confirmEditMember(){
  if(!currentMember)return;
  const data={name:document.getElementById("editMemberName").value.trim(),phone:document.getElementById("editMemberPhone").value.trim(),remark:document.getElementById("editMemberRemark").value.trim()||null};
  if(!data.name||!data.phone){alert("请填写姓名和手机号");return;}
  if(adminToolsVisible){
    const balance=parseFloat(document.getElementById("editMemberBalance").value);
    if(!Number.isFinite(balance)||balance<0){alert("请输入有效余额");return;}
    data.balance=balance;
  }
  try{
    const r=await fetch(API.members+"/"+currentMember.id,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)}),j=await r.json();
    if(j.code===0){closeModal("editMemberModal");fetchMembers();}else alert("修改失败: "+(j.detail||j.msg||"unknown"));
  }catch(e){alert("请求失败: "+e);}
}



async function showRechargeModal(memberId){
  const member=membersData.find(item=>item.id===memberId);if(!member)return;
  currentMember=member;
  try{await loadPerformanceStaff();}catch(e){alert(e.message);return;}
  populatePerformanceStaff("rechargePerformanceStaff");
  document.getElementById("rechargeMemberLabel").textContent=member.name;
  document.getElementById("rechargeAmount").value="";
  document.getElementById("rechargeGiftAmount").value="0";
  document.getElementById("rechargeMethod").value="现金";
  document.getElementById("rechargeBusinessDate").max=_currentBusinessDate();
  document.getElementById("rechargeBusinessDate").value=_currentBusinessDate();
  document.getElementById("rechargeNotes").value="";
  updateRechargePreview();
  showModal("rechargeModal");
}

function updateRechargePreview(){
  const amount=Math.max(0,parseFloat(document.getElementById("rechargeAmount")?.value)||0);
  const gift=Math.max(0,parseFloat(document.getElementById("rechargeGiftAmount")?.value)||0);
  const currentBalance=Number(currentMember?.balance||0);
  document.getElementById("rechargeCreditTotal").textContent=_reportMoney(amount+gift);
  document.getElementById("rechargeBalanceAfter").textContent=_reportMoney(currentBalance+amount+gift);
}

async function confirmRecharge(){
  if(!currentMember)return;
  const performanceStaffId=readPerformanceStaff("rechargePerformanceStaff");if(performanceStaffId===null)return;
  const amount=parseFloat(document.getElementById("rechargeAmount").value);
  const giftAmount=parseFloat(document.getElementById("rechargeGiftAmount").value)||0;
  const method=document.getElementById("rechargeMethod").value;
  const businessDate=document.getElementById("rechargeBusinessDate").value;
  const notes=document.getElementById("rechargeNotes").value.trim()||null;
  if(!amount||amount<=0){alert("请输入有效的充卡金额");return;}
  if(giftAmount<0){alert("赠送金额不能小于0");return;}
  if(!businessDate){alert("请选择归属营业日");return;}
  try{
    const r=await fetch(API.recharge+"/"+currentMember.id+"/recharge",{
      method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({amount,gift_amount:giftAmount,payment_method:method,performance_staff_id:performanceStaffId,business_date:businessDate,notes})
    });
    const j=await r.json();
    if(j.code===0){
      closeModal("rechargeModal");fetchMembers();
      if(activeTab==="recharges")fetchRechargeLogs();
    }else alert("充值失败："+(j.detail||j.msg||"unknown"));
  }catch(e){alert("请求失败: "+e);}
}



function showResetPwdModal(memberId){
  const member=membersData.find(item=>item.id===memberId);if(!member)return;
  currentMember=member;
  document.getElementById("resetPwdLabel").textContent=member.name;
  document.getElementById("resetPwdNew").value="";
  showModal("resetPwdModal");
}

async function confirmResetPwd(){
  if(!currentMember)return;
  const newPwd=document.getElementById("resetPwdNew").value.trim();
  if(!newPwd||newPwd.length<4){alert("新密码至少4位");return;}
  try{
    const r=await fetch(API.resetPwd+"/"+currentMember.id+"/reset-password",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({new_password:newPwd})});
    const j=await r.json();
    if(j.code===0){closeModal("resetPwdModal");alert("密码已重置");}
    else alert("重置失败: "+(j.detail||j.msg||"unknown"));
  }catch(e){alert("请求失败: "+e);}
}
// ================================================================



// Package Management



// ================================================================







async function fetchPackages(){
  try{const r=await fetch(API.packages),j=await r.json();if(j.code===0){packagesData=j.data;renderPackages();}}catch(e){}
}
function onPkgTypeChange(){renderPackages();}
function packageItemSummary(items){
  if(!items||!items.length)return "无附带酒水/小吃";
  return items.map(i=>(i.item_type==="drink"?"酒水：":"小吃：")+i.item_name+"×"+i.qty+(i.unit_label||(i.item_type==="snack"?"份":""))).join("，");
}
function renderPackages(){
  const filter=document.getElementById("pkgTypeFilter").value,filtered=packagesData.filter(p=>p.type===filter),tb=document.querySelector("#packagesTable tbody");
  document.getElementById("pkgTypeLabel").textContent=filter==="open"?"开台套餐":"续时套餐";
  if(!filtered.length){tb.innerHTML='<tr><td colspan="5" class="empty-hint">暂无套餐</td></tr>';return;}
  tb.innerHTML=filtered.map(p=>'<tr><td>'+p.name+'</td><td>'+p.duration_minutes+'</td><td>'+Number(p.price_normal||0).toFixed(2)+'</td><td style="font-size:12px;color:var(--text-dim);">'+packageItemSummary(p.items)+'</td><td><button class="btn btn-xs btn-outline" onclick="showEditPackageModal('+p.id+')">编辑</button> <button class="btn btn-xs btn-danger" onclick="showDeletePkgModal('+p.id+',\''+p.name+'\')">删除</button></td></tr>').join("");
}
function populatePackageDrinkOptions(){
  const drinks=inventoryData.filter(i=>["酒水","饮料"].includes(i.category));
  document.getElementById("pkgDrinkInventory").innerHTML=drinks.length?drinks.map(i=>'<option value="'+i.id+'">'+escapeHtml(i.category+' - '+i.name)+'（库存 '+inventoryStockText(i)+'）</option>').join(""):'<option value="">请先在库存管理新增酒水或饮料</option>';
}
function renderPackageItemEditor(){
  const indexed=editingPackageItems.map((item,index)=>({item,index})),drinks=indexed.filter(x=>x.item.item_type==="drink"),snacks=indexed.filter(x=>x.item.item_type==="snack");
  document.getElementById("pkgDrinkList").innerHTML=drinks.length?drinks.map(x=>'<div style="display:flex;justify-content:space-between;padding:4px 0;"><span>'+x.item.item_name+' × '+x.item.qty+(x.item.unit_label||"瓶")+'</span><button type="button" class="btn btn-xs btn-danger" onclick="removePackageItem('+x.index+')">移除</button></div>').join(""):"暂未添加酒水";
  document.getElementById("pkgSnackList").innerHTML=snacks.length?snacks.map(x=>'<div style="display:flex;justify-content:space-between;padding:4px 0;"><span>'+x.item.item_name+' × '+x.item.qty+'份</span><button type="button" class="btn btn-xs btn-danger" onclick="removePackageItem('+x.index+')">移除</button></div>').join(""):"暂未添加小吃";
}
function showPackageModal(){
  editingPackageItems=[];document.getElementById("packageModalTitle").textContent="新增套餐";document.getElementById("editPackageId").value="";document.getElementById("pkgName").value="";document.getElementById("pkgType").value=document.getElementById("pkgTypeFilter").value;document.getElementById("pkgDuration").value="180";document.getElementById("pkgPriceNormal").value="0";document.getElementById("pkgDrinkQty").value="1";document.getElementById("pkgSnackName").value="";document.getElementById("pkgSnackQty").value="1";populatePackageDrinkOptions();renderPackageItemEditor();showModal("packageModal");
}
function showEditPackageModal(pkgId){
  const p=packagesData.find(x=>x.id===pkgId);if(!p)return;editingPackageItems=(p.items||[]).map(item=>({...item}));document.getElementById("packageModalTitle").textContent="编辑套餐";document.getElementById("editPackageId").value=p.id;document.getElementById("pkgName").value=p.name||"";document.getElementById("pkgType").value=p.type;document.getElementById("pkgDuration").value=p.duration_minutes;document.getElementById("pkgPriceNormal").value=p.price_normal||0;document.getElementById("pkgDrinkQty").value="1";document.getElementById("pkgSnackName").value="";document.getElementById("pkgSnackQty").value="1";populatePackageDrinkOptions();renderPackageItemEditor();showModal("packageModal");
}
function addPackageDrinkItem(){
  const inventoryId=parseInt(document.getElementById("pkgDrinkInventory").value),qty=parseInt(document.getElementById("pkgDrinkQty").value)||1,inventory=inventoryData.find(i=>i.id===inventoryId);if(!inventory){alert("请先选择酒水商品");return;}const existing=editingPackageItems.find(i=>i.item_type==="drink"&&i.inventory_id===inventoryId);if(existing)existing.qty+=qty;else editingPackageItems.push({item_type:"drink",inventory_id:inventoryId,item_name:inventory.name,qty,unit_label:inventory.unit_name||"瓶"});renderPackageItemEditor();
}
function addPackageSnackItem(){
  const name=document.getElementById("pkgSnackName").value.trim(),qty=parseInt(document.getElementById("pkgSnackQty").value)||1;if(!name){alert("请填写小吃名称");return;}const existing=editingPackageItems.find(i=>i.item_type==="snack"&&i.item_name===name);if(existing)existing.qty+=qty;else editingPackageItems.push({item_type:"snack",item_name:name,qty,unit_label:"份"});document.getElementById("pkgSnackName").value="";renderPackageItemEditor();
}
function removePackageItem(index){editingPackageItems.splice(index,1);renderPackageItemEditor();}
async function confirmPackage(){
  const editId=document.getElementById("editPackageId").value,data={name:document.getElementById("pkgName").value.trim(),type:document.getElementById("pkgType").value,duration_minutes:parseInt(document.getElementById("pkgDuration").value)||0,price_normal:parseFloat(document.getElementById("pkgPriceNormal").value)||0,items:editingPackageItems.map(i=>i.item_type==="drink"?{item_type:"drink",inventory_id:i.inventory_id,qty:i.qty}:{item_type:"snack",item_name:i.item_name,qty:i.qty})};
  if(!data.name||data.duration_minutes<1){alert("请填写套餐名称和有效时长");return;}
  try{const r=editId?await fetch(API.packages+"/"+editId,{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)}):await fetch(API.packages,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)}),j=await r.json();if(r.ok&&j.code===0){closeModal("packageModal");fetchPackages();}else alert((editId?"修改":"新增")+"失败: "+(j.detail||j.msg||"unknown"));}catch(e){alert("请求失败: "+e);}
}
function showDeletePkgModal(pkgId,pkgName){document.getElementById("deletePkgName").textContent=pkgName;document.getElementById("deletePkgPassword").value="";document.getElementById("confirmDeletePkg").onclick=async()=>{const pwd=document.getElementById("deletePkgPassword").value;try{const r=await fetch(API.packages+"/"+pkgId,{method:"DELETE",headers:{"Content-Type":"application/json"},body:JSON.stringify({admin_password:pwd})});const j=await r.json();if(j.code===0){closeModal("deletePkgModal");fetchPackages();}else alert("删除失败: "+(j.detail||"unknown"));}catch(e){alert("请求失败: "+e);}};showModal("deletePkgModal");}



async function confirmDeletePkg(){}







// ================================================================



// Inventory



// ================================================================







async function fetchInventory(){
  try{
    const r=await fetch(API.inventory),j=await r.json();
    if(j.code===0){inventoryData=j.data;renderInventory();}
  }catch(e){}
}

const INVENTORY_UNITS={"酒水":"瓶","饮料":"瓶","零食":"份","水果":"份"};
function inventoryUnitFor(category){return INVENTORY_UNITS[category]||"份";}
function inventoryTracksStock(item){return item&&["酒水","饮料"].includes(item.category);}

function onInventoryCategoryChange(){
  const category=document.getElementById("invCategory").value;
  const unit=inventoryUnitFor(category);
  document.getElementById("invUnitName").value=unit;
  document.getElementById("invUnitHint").textContent=unit+"（按分类自动设置）";
  document.getElementById("invStockLabel").textContent="库存总数（"+unit+"）";
  const tracks=category==="酒水"||category==="饮料";
  document.getElementById("invStockHint").textContent=tracks?(category+"销售后自动扣库存"):(category+"只记账，不自动扣库存，数量手动维护");
  const caseFields=document.getElementById("inventoryCaseFields");
  caseFields.style.display=category==="酒水"?"grid":"none";
  if(category!=="酒水"){
    document.getElementById("invCaseSize").value="0";
    document.getElementById("invCasePrice").value="0";
  }
}

function inventoryStockText(item){
  const stock=Number(item.stock||0);
  const unit=item.unit_name||inventoryUnitFor(item.category);
  const caseSize=Number(item.case_size||0);
  if(item.category==="酒水"&&caseSize>=2){
    const cases=Math.floor(stock/caseSize),remainder=stock%caseSize;
    return cases+"箱 "+remainder+unit+"（总"+stock+unit+"）";
  }
  return stock+unit;
}

function renderInventory(){
  const tb=document.querySelector("#inventoryTable tbody");
  if(!inventoryData.length){tb.innerHTML='<tr><td colspan="10" class="empty-hint">暂无库存</td></tr>';return;}
  tb.innerHTML=inventoryData.map(i=>{
    const unit=i.unit_name||inventoryUnitFor(i.category);
    const caseSize=Number(i.case_size||0);
    const hasCase=i.category==="酒水"&&caseSize>=2;
    const caseSpec=hasCase?caseSize+unit+"/箱":"-";
    const casePrice=hasCase?Number(i.case_price||0).toFixed(2):"-";
    const low=inventoryTracksStock(i)&&Number(i.stock||0)<=Number(i.low_stock??5);
    const linkage=inventoryTracksStock(i)?"":"<div class=\"cell-note\">手动维护</div>";
    const storedText=i.category==="酒水"
      ?'<span class="stored-stock-total">总计 '+Number(i.stored_quantity||0)+escapeHtml(unit)+'</span>'
      :'-';
    return '<tr><td>'+escapeHtml(i.category)+'</td><td>'+escapeHtml(i.name)+'</td><td>'+unit+'</td><td>'+Number(i.unit_price||0).toFixed(2)+'</td><td>'+caseSpec+'</td><td>'+casePrice+'</td><td class="admin-only" style="display:none;">'+Number(i.cost_price||0).toFixed(2)+'</td><td style="'+(low?'color:var(--danger);font-weight:700;':'')+'">'+inventoryStockText(i)+linkage+'</td><td>'+storedText+'</td><td><button class="btn btn-xs btn-outline" onclick="showEditInventoryModal('+i.id+')">编辑</button> <button class="btn btn-xs btn-danger del-btn" style="display:none;" onclick="deleteInventory('+i.id+')">删除</button></td></tr>';
  }).join("");
  applyAdminToolsVisibility();
}

function showInventoryModal(){
  document.getElementById("inventoryModalTitle").textContent="新增库存物品";
  document.getElementById("editInvId").value="";
  document.getElementById("invCategory").value="酒水";
  document.getElementById("invName").value="";
  document.getElementById("invPrice").value="0";
  document.getElementById("invCaseSize").value="0";
  document.getElementById("invCasePrice").value="0";
  document.getElementById("invCostPrice").value="0";
  document.getElementById("invStock").value="0";
  document.getElementById("invLowStock").value="5";
  onInventoryCategoryChange();
  showModal("inventoryModal");
  applyAdminToolsVisibility();
}

function showEditInventoryModal(itemId){
  const i=inventoryData.find(x=>x.id===itemId);if(!i)return;
  document.getElementById("inventoryModalTitle").textContent="编辑库存物品";
  document.getElementById("editInvId").value=itemId;
  document.getElementById("invCategory").value=i.category;
  document.getElementById("invName").value=i.name;
  document.getElementById("invPrice").value=Number(i.unit_price||0);
  document.getElementById("invStock").value=Number(i.stock||0);
  document.getElementById("invLowStock").value=Number(i.low_stock??5);
  document.getElementById("invCostPrice").value=Number(i.cost_price||0);
  onInventoryCategoryChange();
  if(i.category==="酒水"){
    document.getElementById("invCaseSize").value=Number(i.case_size||0);
    document.getElementById("invCasePrice").value=Number(i.case_price||0);
  }
  showModal("inventoryModal");
  applyAdminToolsVisibility();
}

async function confirmInventory(){
  const editId=document.getElementById("editInvId").value;
  const category=document.getElementById("invCategory").value;
  const isAlcohol=category==="酒水";
  const data={
    category,
    name:document.getElementById("invName").value.trim(),
    unit_name:inventoryUnitFor(category),
    unit_price:parseFloat(document.getElementById("invPrice").value)||0,
    case_size:isAlcohol?(parseInt(document.getElementById("invCaseSize").value)||0):0,
    case_price:isAlcohol?(parseFloat(document.getElementById("invCasePrice").value)||0):0,
    stock:parseInt(document.getElementById("invStock").value)||0,
    low_stock:parseInt(document.getElementById("invLowStock").value)||0
  };
  if(data.case_size<2){data.case_size=0;data.case_price=0;}
  if(adminToolsVisible)data.cost_price=parseFloat(document.getElementById("invCostPrice").value)||0;
  if(!data.name){alert("请填写物品名称");return;}
  if(editId){
    const original=inventoryData.find(x=>x.id===parseInt(editId));
    if(original&&data.stock!==Number(original.stock||0)){
      const password=prompt("手动修改库存量，请输入管理密码");
      if(!password)return;
      data.admin_password=password;
    }
  }
  try{
    const r=await fetch(editId?API.inventory+"/"+editId:API.inventory,{method:editId?"PUT":"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});
    const j=await r.json();
    if(r.ok&&j.code===0){closeModal("inventoryModal");fetchInventory();}
    else alert("操作失败: "+(j.detail||"unknown"));
  }catch(e){alert("请求失败: "+e);}
}
async function deleteInventory(itemId){
  if(!confirm("确认删除该库存物品？"))return;
  try{
    const r=await fetch(API.inventory+"/"+itemId,{method:"DELETE"}),j=await r.json();
    if(j.code===0)fetchInventory();else alert("删除失败: "+(j.detail||"unknown"));
  }catch(e){alert("请求失败: "+e);}
}

// Staff

// ================================================================

async function fetchStaff(){
  try{
    const r=await fetch(API.staff),j=await r.json();
    if(j.code===0){staffData=j.data;renderStaff();}
  }catch(e){}
}

const staffCommissionDefaults={type:"none",first_limit:10000,second_limit:20000,first_rate:15,second_rate:20,third_rate:25,fixed_rate:20};
const staffCommissionFields={first_limit:"staffFirstLimit",second_limit:"staffSecondLimit",first_rate:"staffFirstRate",second_rate:"staffSecondRate",third_rate:"staffThirdRate",fixed_rate:"staffFixedRate"};

function staffCommissionText(rule){
  const r={...staffCommissionDefaults,...(rule||{})};
  if(r.type==="manager")return "经理：全部业绩 × "+r.fixed_rate+"%";
  if(r.type!=="marketing")return "不计算提成";
  return "营销（阶梯分段）\n前 "+r.first_limit+" 元部分 × "+r.first_rate+"%\n超过 "+r.first_limit+" 至 "+r.second_limit+" 元部分 × "+r.second_rate+"%\n超过 "+r.second_limit+" 元部分 × "+r.third_rate+"%";
}

function readStaffCommissionRule(){
  const rule={type:document.getElementById("staffCommissionType").value};
  Object.entries(staffCommissionFields).forEach(([field,id])=>{rule[field]=parseFloat(document.getElementById(id).value);});
  return rule;
}

function updateStaffCommissionFields(){
  const rule=readStaffCommissionRule();
  document.getElementById("staffMarketingRule").hidden=rule.type!=="marketing";
  document.getElementById("staffManagerRule").hidden=rule.type!=="manager";
  document.getElementById("staffCommissionHint").textContent=staffCommissionText(rule)+(rule.type==="marketing"?"\n按个人当月累计业绩分段计算，不是全部业绩套最高比例。":"");
}

function loadStaffCommissionRule(rule){
  const r={...staffCommissionDefaults,...(rule||{})};
  document.getElementById("staffCommissionType").value=r.type;
  Object.entries(staffCommissionFields).forEach(([field,id])=>{document.getElementById(id).value=r[field];});
  updateStaffCommissionFields();
}

function renderStaff(){
  const tb=document.querySelector("#staffTable tbody");
  if(!staffData.length){tb.innerHTML='<tr><td colspan="8" class="empty-hint">&#26242;&#26080;&#24215;&#20869;&#20154;&#21592;</td></tr>';return;}
  tb.innerHTML=staffData.map(s=>'<tr><td>'+escapeHtml(s.name)+'</td><td>'+escapeHtml(s.phone||'-')+'</td><td>'+escapeHtml(s.position)+'</td><td><span class="status-badge '+(s.status==="\u5728\u804c"?'active':'inactive')+'">'+escapeHtml(s.status)+'</span></td><td class="admin-only" style="display:none;">'+Number(s.salary||0).toFixed(2)+'</td><td class="records-access-only" style="display:none;white-space:pre-line;">'+escapeHtml(staffCommissionText(s.commission_rule))+'</td><td>'+escapeHtml(s.notes||'-')+'</td><td><button class="btn btn-xs btn-outline" onclick="showEditStaffModal('+s.id+')">&#32534;&#36753;</button> <button class="btn btn-xs btn-danger del-btn" style="display:none;" onclick="deleteStaff('+s.id+')">&#21024;&#38500;</button></td></tr>').join("");
  applyAdminToolsVisibility();
  applyRecordsVisibility();
}


function showStaffModal(){
  document.getElementById("staffModalTitle").textContent="\u65b0\u589e\u5e97\u5185\u4eba\u5458";
  document.getElementById("editStaffId").value="";
  document.getElementById("staffName").value="";
  document.getElementById("staffPhone").value="";
  document.getElementById("staffPosition").value="\u5458\u5de5";
  document.getElementById("staffStatus").value="\u5728\u804c";
  document.getElementById("staffSalary").value="0";
  document.getElementById("staffNotes").value="";
  loadStaffCommissionRule();
  showModal("staffModal");
  applyAdminToolsVisibility();
  applyRecordsVisibility();
}


function showEditStaffModal(staffId){
  const s=staffData.find(x=>x.id===staffId);if(!s)return;
  document.getElementById("staffModalTitle").textContent="\u7f16\u8f91\u5e97\u5185\u4eba\u5458";
  document.getElementById("editStaffId").value=staffId;
  document.getElementById("staffName").value=s.name;
  document.getElementById("staffPhone").value=s.phone||"";
  document.getElementById("staffPosition").value=s.position;
  document.getElementById("staffStatus").value=s.status;
  document.getElementById("staffSalary").value=Number(s.salary||0);
  document.getElementById("staffNotes").value=s.notes||"";
  loadStaffCommissionRule(s.commission_rule);
  showModal("staffModal");
  applyAdminToolsVisibility();
  applyRecordsVisibility();
}


async function confirmStaff(){
  const staffId=document.getElementById("editStaffId").value;
  const data={name:document.getElementById("staffName").value.trim(),phone:document.getElementById("staffPhone").value.trim()||null,position:document.getElementById("staffPosition").value.trim(),status:document.getElementById("staffStatus").value,notes:document.getElementById("staffNotes").value.trim()||null};
  if(adminToolsVisible)data.salary=parseFloat(document.getElementById("staffSalary").value)||0;
  if(recordsVisible){
    const rule=readStaffCommissionRule();
    if(!Number.isFinite(rule.first_limit)||!Number.isFinite(rule.second_limit)||rule.first_limit<=0||rule.second_limit<=rule.first_limit){alert("第一档上限必须大于0，第二档上限必须大于第一档上限");return;}
    if([rule.first_rate,rule.second_rate,rule.third_rate,rule.fixed_rate].some(rate=>!Number.isFinite(rate)||rate<0||rate>100)){alert("提成比例必须填写0到100之间的数字");return;}
    data.commission_rule=rule;
  }
  if(!data.name||!data.position){alert("\u8bf7\u586b\u5199\u59d3\u540d\u548c\u5c97\u4f4d");return;}
  try{
    const r=await fetch(staffId?API.staff+"/"+staffId:API.staff,{method:staffId?"PUT":"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});
    const j=await r.json();
    if(j.code===0){closeModal("staffModal");fetchStaff();}else alert("\u64cd\u4f5c\u5931\u8d25: "+(j.detail||"unknown"));
  }catch(e){alert("\u8bf7\u6c42\u5931\u8d25: "+e);}
}

async function deleteStaff(staffId){
  if(!confirm("确认删除这名店内人员？"))return;
  try{const r=await fetch(API.staff+"/"+staffId,{method:"DELETE"}),j=await r.json();if(j.code===0)fetchStaff();else alert("删除失败: "+(j.detail||"unknown"));}catch(e){alert("请求失败: "+e);}
}


// ================================================================



// Billing / Settlement



// ================================================================







function drinkUnitLabel(drink){return drink.unit_label||(drink.sale_unit==="case"?"箱":"瓶");}
function drinkSummaryLine(drink){const label=drinkUnitLabel(drink),price=Number(drink.unit_price||0),subtotal=Number(drink.qty||0)*price,prefix=drink.source==="package"?"[套餐] ":"";return prefix+drink.item_name+" × "+drink.qty+label+" @"+price.toFixed(2)+" = "+subtotal.toFixed(2);}
function renderSettleDrinkSummary(drinks){document.getElementById("settleDrinksSummary").innerHTML=drinks.length?drinks.map(drinkSummaryLine).join("<br>"):"暂无";}
function billingPaymentHtml(bill){
  const payments=bill.payment_breakdown||[];
  if(!payments.length)return escapeHtml(bill.payment_method||"-");
  return '<div class="billing-payment-list">'+payments.map(item=>
    '<div class="billing-payment-item"><span>'+escapeHtml(item.method||"-")+'</span><strong>'+_reportMoney(item.amount)+'</strong></div>'
  ).join("")+'</div>';
}

function billingDrinkListHtml(drinks){
  if(!drinks||!drinks.length)return "-";
  return '<div class="history-drink-list">'+drinks.map(drink=>{
    const prefix=drink.source==="package"?'<span class="cell-note">套餐</span> ':"";
    return '<div>'+prefix+escapeHtml(drink.item_name||"-")+' × '+Number(drink.qty||0)+escapeHtml(drinkUnitLabel(drink))+'</div>';
  }).join("")+'</div>';
}
async function fetchActiveBilling(){try{const r=await fetch(API.billingActive);const j=await r.json();if(j.code===0){activeBillingData=j.data;renderActiveBilling(activeBillingData);}}catch(e){}}

function renderActiveBilling(bills){
  const tb=document.querySelector("#billingTable tbody");
  if(!bills.length){tb.innerHTML='<tr><td colspan="8" class="empty-hint">\u6682\u65e0\u5f00\u53f0\u8d26\u5355</td></tr>';return;}
  tb.innerHTML=bills.map(b=>{
    const ct=b.customer_type==="retail"?"\u6563\u6237":("\u4f1a\u5458(id="+b.member_id+")");
    const received=b.package_id===null||b.package_id===undefined
      ?'<span style="color:var(--text-dim);">\u672a\u4fdd\u5b58</span>'
      :'<strong style="color:var(--accent);">'+Number(b.total||0).toFixed(2)+'</strong>';
    const openTime=b.open_at?String(b.open_at).replace("T"," ").substring(0,19):"-";
    const drinkDetails=billingDrinkListHtml(b.drinks);
    return '<tr><td>'+b.room_no+'</td><td class="cell-time">'+openTime+'</td><td>'+(b.duration_minutes||0)+'</td><td>'+Number(b.drinks_fee||0).toFixed(2)+'</td><td>'+drinkDetails+'</td><td>'+received+'</td><td>'+ct+'</td><td><button class="btn btn-xs btn-accent" onclick="showSettle('+b.id+')">结账</button></td></tr>';
  }).join("");
}


async function loadPerformanceStaff(){
  const response=await fetch(API.staff),json=await response.json();
  if(!response.ok||json.code!==0)throw new Error("业绩归属人员加载失败");
  staffData=json.data||[];
}

function populatePerformanceStaff(selectId,bill={},history=false){
  const select=document.getElementById(selectId);
  const eligible=staffData.filter(person=>["marketing","manager"].includes(person.commission_rule?.type)&&(history||person.status==="在职"));
  select.innerHTML='<option value="">-- 请选择人员或无 --</option><option value="0">无</option>'+eligible.map(person=>'<option value="'+person.id+'">'+escapeHtml(person.name)+'（'+(person.commission_rule.type==="manager"?"经理":"营销")+(person.status!=="在职"?" · 已离职":"")+'）</option>').join("");
  const id=bill.performance_staff_id;
  if(history&&id>0&&!eligible.some(person=>person.id===Number(id))){
    const option=document.createElement("option");option.value=String(id);option.textContent=(bill.performance_staff_name||"历史人员")+"（历史归属）";select.appendChild(option);
  }
  select.value=id===null||id===undefined?(history?"0":""):String(id);
}

function readPerformanceStaff(selectId){
  const select=document.getElementById(selectId);
  if(select.value===""){alert("请选择业绩归属人员，没有归属也必须选择无");select.focus();return null;}
  return Number(select.value);
}

function showSettle(billingId){



  fetch(API.billingActive).then(r=>r.json()).then(async json=>{



    if(json.code!==0){alert("\u6253\u5f00\u7ed3\u8d26\u5931\u8d25: "+(json.detail||"unknown"));return;}
    const bill=(json.data||[]).find(b=>Number(b.id)===Number(billingId));
    if(!bill){alert("\u8d26\u5355\u4e0d\u5b58\u5728\u6216\u5df2\u7ed3\u8d26");fetchActiveBilling();return;}



    currentBilling=bill;
    await loadPerformanceStaff();
    populatePerformanceStaff("settlePerformanceStaff",bill);



    document.getElementById("settleRoomLabel").textContent=bill.room_no;



    const pkgSel=document.getElementById("settlePackage");



    const pkgs=packagesData.filter(p=>p.type==="open");



    pkgSel.innerHTML='<option value="">-- 请选择套餐 --</option>'+pkgs.map(p=>'<option value="'+p.id+'">'+p.name+' ('+p.duration_minutes+'min)</option>').join("");

    pkgSel.value=bill.package_id||"";



    document.getElementById("settleDrinksFee").textContent=(bill.drinks_fee||0).toFixed(2);



    const drinks=bill.drinks||[];



    renderSettleDrinkSummary(drinks);



    const savedPayments=bill.payment_breakdown||[];
    const savedIsCombo=savedPayments.length>1;
    document.getElementById("settlePayment").value=savedIsCombo?"组合支付":(bill.payment_method||"");
    document.querySelectorAll("[data-split-method]").forEach(input=>{
      const saved=savedPayments.find(item=>item.method===input.dataset.splitMethod);
      input.value=saved?Number(saved.amount||0).toFixed(2):"0";
    });
    document.getElementById("splitPaymentPanel").style.display=savedIsCombo?"block":"none";
    document.getElementById("settleNotes").value=bill.notes||"";

    document.getElementById("memberSettleInfo").style.display=bill.payment_method==="会员余额"?"block":"none";



    document.getElementById("settleMemberPhone").value=bill.draft_member_phone||"";
    document.getElementById("settleMemberPassword").value="";
    document.getElementById("settleMemberLabel").textContent="";
    if(bill.payment_method==="会员余额"&&bill.draft_member_phone)lookupSettleMember(true);



    const actualInput=document.getElementById("settleActualTotal");
    const savedTotal=Number(bill.total||0);
    const selectedPackage=packagesData.find(p=>p.id===parseInt(pkgSel.value));
    const currentExpected=Number(_getPkgPrice(selectedPackage)||0)+Number(bill.drinks_fee||0);
    const hasSavedDraft=bill.package_id!==null&&bill.package_id!==undefined;
    actualInput.value=hasSavedDraft?savedTotal.toFixed(2):"";
    actualInput.dataset.manual=hasSavedDraft&&Math.abs(savedTotal-currentExpected)>=0.01?"1":"0";



    document.getElementById("settleCard").style.display="block";



    updateSettleTotal();



  }).catch(e=>alert("\u6253\u5f00\u7ed3\u8d26\u5931\u8d25: "+e.message));



}







function hideSettle(){document.getElementById("settleCard").style.display="none";currentBilling=null;}





function _getPkgPrice(pkg){
  return pkg ? parseFloat(pkg.price_normal||0) : 0;
}

function renderSelectedPackageItems(pkg){document.getElementById("settlePackageItems").textContent="套餐内容："+(pkg?packageItemSummary(pkg.items):"暂无");}
function updateSettleTotal(){
  const pkgId=parseInt(document.getElementById("settlePackage").value);
  const pkg=packagesData.find(p=>p.id===pkgId);
  const actualInput=document.getElementById("settleActualTotal");
  renderSelectedPackageItems(pkg);
  if(!pkg){
    document.getElementById("settleRoomFee").textContent="0.00";
    document.getElementById("settleTotal").textContent="0.00";
    if(actualInput.dataset.manual!=="1")actualInput.value="0.00";
    updateSettlePriceHint();
    updateSplitPaymentSummary();
    return;
  }
  const roomFee=_getPkgPrice(pkg);
  const drinksFee=parseFloat(document.getElementById("settleDrinksFee").textContent)||0;
  const subtotal=Math.round((roomFee+drinksFee)*100)/100;
  document.getElementById("settleRoomFee").textContent=roomFee.toFixed(2);
  document.getElementById("settleTotal").textContent=subtotal.toFixed(2);
  if(actualInput.dataset.manual!=="1")actualInput.value=subtotal.toFixed(2);
  updateSettlePriceHint();
  updateSplitPaymentSummary();
}


function onSettleActualPriceInput(){
  document.getElementById("settleActualTotal").dataset.manual="1";
  updateSettlePriceHint();
  updateSplitPaymentSummary();
}


function updateSettlePriceHint(){
  const expected=parseFloat(document.getElementById("settleTotal").textContent)||0;
  const actual=parseFloat(document.getElementById("settleActualTotal").value);
  const notes=document.getElementById("settleNotes").value.trim();
  const hint=document.getElementById("settlePriceHint");
  if(!Number.isFinite(actual)||actual<0){
    hint.textContent="请输入有效的实际收银价格";
    hint.style.color="var(--warning)";
    return;
  }
  if(Math.abs(actual-expected)<0.01){
    hint.textContent="实际收银价格与应收合计一致";
    hint.style.color="var(--text-dim)";
    return;
  }
  const remaining=Math.max(0,10-notes.length);
  hint.textContent=remaining>0?"价格已修改，备注还需填写 "+remaining+" 个字":"价格已修改，备注已满足10字要求";
  hint.style.color=remaining>0?"var(--warning)":"var(--accent)";
}


function getSettlementPricePayload(){
  const expected=parseFloat(document.getElementById("settleTotal").textContent)||0;
  const actual=parseFloat(document.getElementById("settleActualTotal").value);
  const notes=document.getElementById("settleNotes").value.trim();
  if(!Number.isFinite(actual)||actual<0){alert("请输入有效的实际收银价格");return null;}
  if(Math.abs(actual-expected)>=0.01&&notes.length<10){alert("修改实际收银价格后，备注必须填写且至少10个字");document.getElementById("settleNotes").focus();return null;}
  return {actual_total:actual,notes:notes||null};
}


function collectPaymentSplits(){
  return Array.from(document.querySelectorAll("[data-split-method]")).map(input=>({
    payment_method:input.dataset.splitMethod,
    amount:Math.round((parseFloat(input.value)||0)*100)/100
  })).filter(item=>item.amount>0);
}

function updateSplitPaymentSummary(){
  const panel=document.getElementById("splitPaymentPanel");
  if(!panel)return;
  const splitTotal=Math.round(collectPaymentSplits().reduce((sum,item)=>sum+item.amount,0)*100)/100;
  const actual=parseFloat(document.getElementById("settleActualTotal").value)||0;
  const difference=Math.round((actual-splitTotal)*100)/100;
  document.getElementById("splitPaymentTotal").textContent=_reportMoney(splitTotal);
  document.getElementById("splitPaymentDifferenceLabel").textContent=difference>=0?"还差":"超出";
  document.getElementById("splitPaymentRemaining").textContent=_reportMoney(Math.abs(difference));
}

function onSettlePaymentChange(){
  const v=document.getElementById("settlePayment").value;
  document.getElementById("splitPaymentPanel").style.display=v==="组合支付"?"block":"none";
  document.getElementById("memberSettleInfo").style.display=v==="会员余额"?"block":"none";
  updateSplitPaymentSummary();
}

function lookupSettleMember(silent=false){

  const phone=document.getElementById("settleMemberPhone").value.trim();

  if(!phone){if(!silent)alert("请输入会员手机号");return;}

  fetch("/api/members/verify",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({phone,password:""})})

    .then(r=>r.json()).then(j=>{

      if(j.code===0){document.getElementById("settleMemberLabel").textContent="会员: "+j.data.name+"，余额: "+j.data.balance;}

      else if(!silent){alert(j.detail||"查找失败");}

    }).catch(e=>{if(!silent)alert("查找失败: "+e);});

}















async function saveSettlementDraft(){
  if(!currentBilling)return;
  const performanceStaffId=readPerformanceStaff("settlePerformanceStaff");if(performanceStaffId===null)return;
  const packageId=parseInt(document.getElementById("settlePackage").value);
  if(!packageId){alert("请选择套餐");return;}
  const pricing=getSettlementPricePayload();if(!pricing)return;
  const selectedPayment=document.getElementById("settlePayment").value;
  const memberPhone=document.getElementById("settleMemberPhone").value.trim();
  if(selectedPayment==="会员余额"&&!memberPhone){alert("会员余额支付必须填写会员手机号");document.getElementById("settleMemberPhone").focus();return;}
  const paymentSplits=selectedPayment==="组合支付"?collectPaymentSplits():[];
  if(selectedPayment==="组合支付"){
    if(paymentSplits.length<2){alert("组合支付至少填写两种支付方式的金额");return;}
    const splitTotal=Math.round(paymentSplits.reduce((sum,item)=>sum+item.amount,0)*100)/100;
    if(Math.abs(splitTotal-pricing.actual_total)>=0.01){alert("组合支付合计必须等于实收金额，当前合计："+splitTotal.toFixed(2));return;}
  }
  const data={
    package_id:packageId,
    performance_staff_id:performanceStaffId,
    payment_method:selectedPayment==="组合支付"?null:(selectedPayment||null),
    payment_splits:paymentSplits,
    member_phone:selectedPayment==="会员余额"?memberPhone:null,
    actual_total:pricing.actual_total,
    notes:pricing.notes
  };
  try{
    const r=await fetch(API.billingDraft+"/"+currentBilling.id+"/draft",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)}),j=await r.json();
    if(!r.ok||j.code!==0){alert("保存失败: "+(j.detail||"unknown"));return;}
    Object.assign(currentBilling,j);
    currentBilling.drinks=j.drinks||[];
    document.getElementById("settleDrinksFee").textContent=Number(j.drinks_fee||0).toFixed(2);
    document.getElementById("settleActualTotal").value=Number(j.total||0).toFixed(2);
    document.getElementById("settleActualTotal").dataset.manual=j.price_modified?"1":"0";
    document.getElementById("settleNotes").value=j.notes||"";
    document.getElementById("settleMemberPhone").value=j.draft_member_phone||"";
    document.getElementById("settleMemberLabel").textContent=j.draft_member_name
      ?"会员: "+j.draft_member_name+"，余额: "+Number(j.draft_member_balance||0).toFixed(2)
      :"";
    renderSettleDrinkSummary(currentBilling.drinks);
    updateSettleTotal();
    fetchActiveBilling();fetchInventory();
    alert("当前账单版本已保存，套餐酒水库存已同步，尚未结账");
  }catch(e){alert("请求失败: "+e);}
}


async function confirmSettle(){



  if(!currentBilling)return;
  const performanceStaffId=readPerformanceStaff("settlePerformanceStaff");if(performanceStaffId===null)return;



  const pkgId=parseInt(document.getElementById("settlePackage").value);



  if(!pkgId){alert("请选择套餐");return;}



  const payment=document.getElementById("settlePayment").value;
  if(!payment){alert("请选择支付方式");document.getElementById("settlePayment").focus();return;}



  const pricing=getSettlementPricePayload();if(!pricing)return;

  const paymentSplits=payment==="组合支付"?collectPaymentSplits():[];
  if(payment==="组合支付"){
    if(paymentSplits.length<2){alert("组合支付至少填写两种支付方式的金额");return;}
    const splitTotal=Math.round(paymentSplits.reduce((sum,item)=>sum+item.amount,0)*100)/100;
    if(Math.abs(splitTotal-pricing.actual_total)>=0.01){alert("组合支付合计必须等于实收金额，当前合计："+splitTotal.toFixed(2));return;}
  }

  let mp="";



  if(payment==="会员余额")mp=document.getElementById("settleMemberPassword").value;



  try{const r=await fetch(API.settle,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({billing_id:currentBilling.id,package_id:pkgId,performance_staff_id:performanceStaffId,payment_method:payment==="组合支付"?null:payment,payment_splits:paymentSplits,actual_total:pricing.actual_total,member_phone:document.getElementById("settleMemberPhone").value,member_password:mp,notes:pricing.notes})});const j=await r.json();if(j.code===0){const msg="结账成功！总计："+j.total.toFixed(2);alert(msg);hideSettle();fetchActiveBilling();fetchRooms();if(activeTab==="members")fetchMembers();fetchBillingHistory();}else alert("结账失败: "+(j.detail||"unknown"));}



  catch(e){alert("请求失败: "+e);}



}







// ================================================================



// Operation Logs



// ================================================================







function initOperationLogs(){
  const input=document.getElementById("logsDate");
  if(!input.value)input.value=_currentBusinessDate();
  fetchOpLogs();
}

function setLogsToday(){
  document.getElementById("logsDate").value=_currentBusinessDate();
  fetchOpLogs();
}

function changeLogsDate(offset){
  const input=document.getElementById("logsDate");
  const parts=(input.value||_currentBusinessDate()).split("-").map(Number);
  const date=new Date(parts[0],parts[1]-1,parts[2]);
  date.setDate(date.getDate()+offset);
  input.value=_localDateText(date);
  fetchOpLogs();
}

async function fetchOpLogs(){
  const input=document.getElementById("logsDate");
  const date=input.value||_currentBusinessDate();
  input.value=date;
  try{
    const url=API.operationLogs+"?date="+encodeURIComponent(date)+"&limit=1000";
    const response=await fetch(url,{headers:{"X-Records-Password":recordsSessionPassword}});
    const json=await response.json();
    if(!response.ok||json.code!==0)throw new Error(json.detail||"操作日志加载失败");
    document.getElementById("logsRange").textContent="统计范围："+json.start_at+" 至 "+json.end_at+"（不含结束时间）";
    renderOpLogs(json.data||[]);
  }catch(e){
    document.querySelector("#logsTable tbody").innerHTML='<tr><td colspan="4" class="empty-hint">日志加载失败：'+escapeHtml(e.message)+'</td></tr>';
  }
}



function renderOpLogs(logs){const tb=document.querySelector("#logsTable tbody");if(!logs.length){tb.innerHTML='<tr><td colspan="4" class="empty-hint">暂无日志</td></tr>';return;}const labels={open_room:"开台",close_room:"关台",extend_room:"",auto_close:"定时关台",create_booking:"预",cancel_booking:"取消预订",booking_open:"预订开台",booking_failed:"预订失败",create_member:"新增会员",update_member:"编辑会员",recharge_member:"会员充值",reset_member_password:"重置密码",create_package:"新增套餐",update_package:"改",delete_package:"删除套餐",create_staff:"新增店内人员",update_staff:"编辑店内人员",delete_staff:"删除店内人员",create_inventory:"新库",update_inventory:"改库",delete_inventory:"删除库存",add_drink:"添加酒水",update_billing:"编辑账单",save_billing_draft:"保存账单",settle_billing:"结账",store_member_drink:"会员存酒",retrieve_member_drink:"会员取酒",expire_drink_to_inventory:"过期存酒转库存",extend_expired_drink:"过期存酒延期",create_billing_history:"新增结账记录",update_billing_history:"修改结账记录",create_recharge_log:"新增充卡流水",update_recharge_log:"修改充卡流水",delete_recharge_log:"删除充卡流水"};tb.innerHTML=logs.map(l=>{const t=l.created_at?l.created_at.replace("T"," ").substring(0,19):"-";return '<tr><td style="font-size:12px;color:var(--text-dim);white-space:nowrap;">'+t+'</td><td>'+(labels[l.action]||l.action)+'</td><td>'+(l.room_no||"-")+'</td><td style="font-size:13px;color:var(--text-dim);">'+(l.detail||"-")+'</td></tr>';}).join("");}







// ================================================================



// Billing History



// ================================================================







function initBillingHistory(){
  const input=document.getElementById("historyDate");
  if(!input.value)input.value=_currentBusinessDate();
  fetchBillingHistory();
}

function setHistoryToday(){
  document.getElementById("historyDate").value=_currentBusinessDate();
  fetchBillingHistory();
}

function changeHistoryDate(offset){
  const input=document.getElementById("historyDate");
  const parts=(input.value||_currentBusinessDate()).split("-").map(Number);
  const date=new Date(parts[0],parts[1]-1,parts[2]);
  date.setDate(date.getDate()+offset);
  input.value=_localDateText(date);
  fetchBillingHistory();
}

async function fetchBillingHistory(){
  const input=document.getElementById("historyDate");
  const date=input.value||_currentBusinessDate();
  input.value=date;
  try{
    const response=await fetch(API.billingHistory+"?date="+encodeURIComponent(date)),json=await response.json();
    if(!response.ok||json.code!==0)throw new Error(json.detail||"结账记录加载失败");
    billingHistoryData=(json.data||[]).sort((a,b)=>_historyTimeValue(b.open_at||b.close_at)-_historyTimeValue(a.open_at||a.close_at)||b.id-a.id);
    document.getElementById("historyRange").textContent="统计范围："+json.start_at+" 至 "+json.end_at+"（不含结束时间）";
    renderBillingHistory(billingHistoryData);
  }catch(e){
    document.querySelector("#historyTable tbody").innerHTML='<tr><td colspan="12" class="empty-hint">记录加载失败：'+escapeHtml(e.message)+'</td></tr>';
  }
}


async function fetchRechargeLogs(){
  try{
    const response=await fetch(API.rechargeLogs,{headers:{"X-Records-Password":recordsSessionPassword}}),json=await response.json();
    if(!response.ok||json.code!==0)throw new Error(json.detail||"充卡记录加载失败");
    rechargeLogsData=(json.data||[]).sort((a,b)=>String(b.business_date||"").localeCompare(String(a.business_date||""))||_historyTimeValue(b.created_at)-_historyTimeValue(a.created_at)||b.id-a.id);
    renderRechargeLogs(rechargeLogsData);
  }catch(e){
    document.querySelector("#rechargeLogsTable tbody").innerHTML='<tr><td colspan="11" class="empty-hint">记录加载失败：'+escapeHtml(e.message)+'</td></tr>';
  }
}


function _historyTimeValue(value){
  if(!value)return 0;
  const parsed=Date.parse(String(value).replace(" ","T"));
  return Number.isFinite(parsed)?parsed:0;
}


function renderBillingHistory(bills){
  const tb=document.querySelector("#historyTable tbody");
  if(!bills.length){tb.innerHTML='<tr><td colspan="12" class="empty-hint">暂无记录</td></tr>';return;}
  tb.innerHTML=bills.map(b=>{
    const openTime=b.open_at?String(b.open_at).replace("T"," ").substring(0,19):(b.close_at?String(b.close_at).replace("T"," ").substring(0,19):"-");
    const closeTime=b.close_at?String(b.close_at).replace("T"," ").substring(0,19):"-";
    const member=b.settlement_member_name?escapeHtml(b.settlement_member_name)+'<div style="font-size:11px;color:var(--text-dim);">'+escapeHtml(b.settlement_member_phone||"")+'</div>':"-";
    const drinks=b.drinks||[];
    const drinkDetails=drinks.length?'<div class="history-drink-list">'+drinks.map(item=>{
      const qty=Number(item.qty||0);
      const unit=escapeHtml(item.unit_label||"");
      const amount=qty*Number(item.unit_price||0);
      const priceLabel=amount>0?_reportMoney(amount):(item.source==="package"?"套餐内":"赠送");
      return '<div class="history-drink-item"><span>'+escapeHtml(item.item_name||"-")+' × '+qty+unit+'</span><small>'+priceLabel+'</small></div>';
    }).join("")+'</div>':"-";
    const actions='<button class="btn btn-xs btn-outline admin-only" style="display:none;" onclick="showBillingHistoryModal('+b.id+')">修改</button> <button class="btn btn-xs btn-danger admin-only" style="display:none;" onclick="deleteBilling('+b.id+')">删除</button>';
    return '<tr><td>'+escapeHtml(b.room_no||"-")+'</td><td class="cell-time">'+openTime+'</td><td class="cell-time">'+closeTime+'</td><td>'+Number(b.room_fee||0).toFixed(2)+'</td><td>'+Number(b.drinks_fee||0).toFixed(2)+'</td><td>'+drinkDetails+'</td><td>'+Number(b.total||0).toFixed(2)+'</td><td>'+billingPaymentHtml(b)+'</td><td>'+escapeHtml(b.performance_staff_name||(b.performance_staff_id===null||b.performance_staff_id===undefined?"未归属":"无"))+'</td><td>'+member+'</td><td>'+escapeHtml(b.notes||"-")+'</td><td class="del-col" style="display:none;">'+actions+'</td></tr>';
  }).join("");
  applyAdminToolsVisibility();
}


function renderRechargeLogs(logs){
  const tb=document.querySelector("#rechargeLogsTable tbody");
  if(!logs.length){tb.innerHTML='<tr><td colspan="11" class="empty-hint">暂无记录</td></tr>';return;}
  tb.innerHTML=logs.map(r=>{
    const t=r.created_at?String(r.created_at).replace("T"," ").substring(0,19):"-";
    const member=escapeHtml(r.member_name||"-")+'<div style="font-size:11px;color:var(--text-dim);">'+escapeHtml(r.member_phone||"-")+'</div>';
    const balance=r.balance_after==null?"-":Number(r.balance_after).toFixed(2);
    const actions='<button class="btn btn-xs btn-outline admin-only" style="display:none;" onclick="showRechargeLogModal('+r.id+')">修改</button> <button class="btn btn-xs btn-danger admin-only" style="display:none;" onclick="deleteRechargeLog('+r.id+')">删除</button>';
    return '<tr><td>'+member+'</td><td>'+escapeHtml(r.detail||"会员充卡")+'</td><td>'+Number(r.amount||0).toFixed(2)+'</td><td>'+Number(r.gift_amount||0).toFixed(2)+'</td><td>'+balance+'</td><td>'+escapeHtml(r.payment_method||"-")+'</td><td>'+escapeHtml(r.performance_staff_name||(r.performance_staff_id===null||r.performance_staff_id===undefined?"未归属":"无"))+'</td><td>'+escapeHtml(r.business_date||"-")+'</td><td>'+escapeHtml(r.notes||"-")+'</td><td style="font-size:12px;color:var(--text-dim);">'+t+'</td><td class="del-col" style="display:none;">'+actions+'</td></tr>';
  }).join("");
  applyAdminToolsVisibility();
}


function _nowForDateTimeInput(){
  const now=new Date();
  return new Date(now.getTime()-now.getTimezoneOffset()*60000).toISOString().slice(0,19);
}


function _toDateTimeInput(value){
  return value?String(value).replace(" ","T").substring(0,19):_nowForDateTimeInput();
}


async function showBillingHistoryModal(billingId=null){
  if(!adminToolsVisible||!adminSessionPassword){alert("请先按 Ctrl+/ 验证管理密码");return;}
  editingBillingHistoryId=billingId;
  const bill=billingId==null?null:billingHistoryData.find(item=>item.id===billingId);
  try{await loadPerformanceStaff();}catch(e){alert(e.message);return;}
  populatePerformanceStaff("billingHistoryPerformanceStaff",bill||{},true);
  document.getElementById("billingHistoryModalTitle").textContent=bill?"修改结账记录":"新增结账记录";
  document.getElementById("billingHistoryRoom").value=bill?.room_no||"";
  document.getElementById("billingHistoryRoomFee").value=bill?Number(bill.room_fee||0).toFixed(2):"0.00";
  document.getElementById("billingHistoryDrinksFee").value=bill?Number(bill.drinks_fee||0).toFixed(2):"0.00";
  document.getElementById("billingHistoryTotal").value=bill?Number(bill.total||0).toFixed(2):"0.00";
  document.getElementById("billingHistoryPayment").value=bill?.payment_method||"现金";
  document.getElementById("billingHistoryMember").value=bill?.settlement_member_name||"";
  document.getElementById("billingHistoryMemberPhone").value=bill?.settlement_member_phone||"";
  document.getElementById("billingHistoryNotes").value=bill?.notes||"";
  document.getElementById("billingHistoryOpenTime").value=_toDateTimeInput(bill?.open_at||bill?.close_at);
  document.getElementById("billingHistoryTime").value=_toDateTimeInput(bill?.close_at);
  showModal("billingHistoryModal");
}


async function confirmBillingHistory(){
  if(!adminToolsVisible||!adminSessionPassword){alert("管理模式已关闭，请重新验证");return;}
  const performanceStaffId=readPerformanceStaff("billingHistoryPerformanceStaff");if(performanceStaffId===null)return;
  const data={
    room_no:document.getElementById("billingHistoryRoom").value.trim(),
    performance_staff_id:performanceStaffId,
    room_fee:parseFloat(document.getElementById("billingHistoryRoomFee").value),
    drinks_fee:parseFloat(document.getElementById("billingHistoryDrinksFee").value),
    total:parseFloat(document.getElementById("billingHistoryTotal").value),
    payment_method:document.getElementById("billingHistoryPayment").value.trim(),
    settlement_member_name:document.getElementById("billingHistoryMember").value.trim()||null,
    settlement_member_phone:document.getElementById("billingHistoryMemberPhone").value.trim()||null,
    notes:document.getElementById("billingHistoryNotes").value.trim()||null,
    open_at:document.getElementById("billingHistoryOpenTime").value,
    close_at:document.getElementById("billingHistoryTime").value,
    admin_password:adminSessionPassword
  };
  if(!data.room_no||!data.payment_method||!data.open_at||!data.close_at||![data.room_fee,data.drinks_fee,data.total].every(v=>Number.isFinite(v)&&v>=0)){alert("请完整填写有效字段");return;}
  if(new Date(data.open_at)>new Date(data.close_at)){alert("开台时间不能晚于结账时间");return;}
  const url=editingBillingHistoryId==null?API.billingHistory:API.billingHistory+"/"+editingBillingHistoryId;
  try{
    const r=await fetch(url,{method:editingBillingHistoryId==null?"POST":"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)}),j=await r.json();
    if(!r.ok||j.code!==0){alert("保存失败: "+(j.detail||j.msg||"unknown"));return;}
    closeModal("billingHistoryModal");editingBillingHistoryId=null;fetchBillingHistory();
  }catch(e){alert("请求失败: "+e);}
}


async function showRechargeLogModal(logId=null){
  if(!adminToolsVisible||!adminSessionPassword){alert("请先按 Ctrl+/ 验证管理密码");return;}
  if(!membersData.length)await fetchMembers();
  if(!membersData.length){alert("请先添加会员");return;}
  try{await loadPerformanceStaff();}catch(e){alert(e.message);return;}
  editingRechargeLogId=logId;
  const select=document.getElementById("rechargeLogMember");
  select.innerHTML=membersData.map(m=>'<option value="'+m.id+'">'+escapeHtml(m.name)+'（'+escapeHtml(m.phone)+'）</option>').join("");
  const log=logId==null?null:rechargeLogsData.find(r=>r.id===logId);
  populatePerformanceStaff("rechargeLogPerformanceStaff",log||{},true);
  document.getElementById("rechargeLogBusinessDate").max=_currentBusinessDate();
  document.getElementById("rechargeLogModalTitle").textContent=log?"修改充卡记录":"新增充卡记录";
  if(log){
    select.value=String(log.member_id);
    document.getElementById("rechargeLogMemberName").value=log.member_name||"";
    document.getElementById("rechargeLogMemberPhone").value=log.member_phone||"";
    document.getElementById("rechargeLogAmount").value=Number(log.amount||0).toFixed(2);
    document.getElementById("rechargeLogGiftAmount").value=Number(log.gift_amount||0).toFixed(2);
    document.getElementById("rechargeLogBalance").value=log.balance_after==null?"":Number(log.balance_after).toFixed(2);
    document.getElementById("rechargeLogDetail").value=log.detail||"会员充卡";
    document.getElementById("rechargeLogMethod").value=log.payment_method||"现金";
    document.getElementById("rechargeLogBusinessDate").value=log.business_date||_currentBusinessDate();
    document.getElementById("rechargeLogNotes").value=log.notes||"";
    document.getElementById("rechargeLogTime").value=_toDateTimeInput(log.created_at);
  }else{
    onRechargeLogMemberChange();
    document.getElementById("rechargeLogAmount").value="";
    document.getElementById("rechargeLogGiftAmount").value="0";
    document.getElementById("rechargeLogBalance").value=Number(membersData[0].balance||0).toFixed(2);
    document.getElementById("rechargeLogDetail").value="会员充卡";
    document.getElementById("rechargeLogMethod").value="现金";
    document.getElementById("rechargeLogBusinessDate").value=_currentBusinessDate();
    document.getElementById("rechargeLogNotes").value="";
    document.getElementById("rechargeLogTime").value=_nowForDateTimeInput();
  }
  showModal("rechargeLogModal");
}


function onRechargeLogMemberChange(){
  const memberId=parseInt(document.getElementById("rechargeLogMember").value);
  const member=membersData.find(m=>m.id===memberId);if(!member)return;
  document.getElementById("rechargeLogMemberName").value=member.name||"";
  document.getElementById("rechargeLogMemberPhone").value=member.phone||"";
  if(editingRechargeLogId==null)document.getElementById("rechargeLogBalance").value=Number(member.balance||0).toFixed(2);
}


async function confirmRechargeLog(){
  if(!adminToolsVisible||!adminSessionPassword){alert("管理模式已关闭，请重新验证");return;}
  const performanceStaffId=readPerformanceStaff("rechargeLogPerformanceStaff");if(performanceStaffId===null)return;
  const data={
    performance_staff_id:performanceStaffId,
    member_id:parseInt(document.getElementById("rechargeLogMember").value),
    member_name:document.getElementById("rechargeLogMemberName").value.trim(),
    member_phone:document.getElementById("rechargeLogMemberPhone").value.trim(),
    detail:document.getElementById("rechargeLogDetail").value.trim(),
    amount:parseFloat(document.getElementById("rechargeLogAmount").value),
    gift_amount:parseFloat(document.getElementById("rechargeLogGiftAmount").value)||0,
    balance_after:parseFloat(document.getElementById("rechargeLogBalance").value),
    payment_method:document.getElementById("rechargeLogMethod").value.trim(),
    business_date:document.getElementById("rechargeLogBusinessDate").value,
    notes:document.getElementById("rechargeLogNotes").value.trim()||null,
    created_at:document.getElementById("rechargeLogTime").value,
    admin_password:adminSessionPassword
  };
  if(!data.member_id||!data.member_name||!data.member_phone||!data.detail||!data.payment_method||!data.business_date||!Number.isFinite(data.amount)||data.amount<=0||!Number.isFinite(data.gift_amount)||data.gift_amount<0||!Number.isFinite(data.balance_after)||data.balance_after<0||!data.created_at){alert("请完整填写有效字段");return;}
  const url=editingRechargeLogId==null?API.rechargeLogs:API.rechargeLogs+"/"+editingRechargeLogId;
  try{
    const r=await fetch(url,{method:editingRechargeLogId==null?"POST":"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)}),j=await r.json();
    if(!r.ok||j.code!==0){alert("保存失败: "+(j.detail||j.msg||"unknown"));return;}
    closeModal("rechargeLogModal");editingRechargeLogId=null;fetchRechargeLogs();
  }catch(e){alert("请求失败: "+e);}
}


async function deleteRechargeLog(logId){
  if(!adminToolsVisible||!adminSessionPassword){alert("请先按 Ctrl+/ 验证管理密码");return;}
  if(!confirm("确认删除这条充卡记录？该操作不会修改会员当前余额。"))return;
  try{
    const r=await fetch(API.rechargeLogs+"/"+logId+"?admin_password="+encodeURIComponent(adminSessionPassword),{method:"DELETE"}),j=await r.json();
    if(!r.ok||j.code!==0){alert("删除失败: "+(j.detail||j.msg||"unknown"));return;}
    fetchRechargeLogs();
  }catch(e){alert("请求失败: "+e);}
}


async function deleteBilling(billingId){
  if(!adminToolsVisible||!adminSessionPassword){alert("请先按 Ctrl+/ 验证管理密码");return;}
  if(!confirm("确认删除该结账记录？该操作只删除历史记录。"))return;
  try{
    const r=await fetch(API.billingDelete+"/"+billingId+"?admin_password="+encodeURIComponent(adminSessionPassword),{method:"DELETE"}),j=await r.json();
    if(!r.ok||j.code!==0){alert("删除失败: "+(j.detail||j.msg||"unknown"));return;}
    fetchBillingHistory();
  }catch(e){alert("请求失败: "+e);}
}


// ---- Room lock: check unpaid bills before opening ----



async function checkRoomBillable(roomNo){
  try{
    const r=await fetch(API.billingActive),j=await r.json();
    if(!r.ok||j.code!==0)throw new Error(j.detail||"当前账单接口异常");
    const bill=j.data.find(x=>x.room_no===roomNo);
    if(bill){alert("房间 "+roomNo+" 有待结账账单，请先在收银台结清后再开台。");switchTab("checkout");return false;}
    return true;
  }catch(e){
    alert("无法检查房间账单："+e.message+"。为避免重复开台，本次操作已取消。");
    return false;
  }
}







// ================================================================



// Drinks Modal



// ================================================================







async function showDrinksModal(){
  if(!currentBilling)return;
  document.getElementById("drinksRoomLabel").textContent=currentBilling.room_no;
  try{
    const [billingResponse,inventoryResponse]=await Promise.all([fetch(API.billingActive),fetch(API.inventory)]);
    const billingJson=await billingResponse.json(),inventoryJson=await inventoryResponse.json();
    if(billingJson.code!==0||inventoryJson.code!==0)return;
    const bill=billingJson.data.find(b=>b.id===currentBilling.id);
    if(!bill)return;
    currentBilling=bill;
    inventoryData=inventoryJson.data;
    renderDrinksEditTable(bill.drinks||[]);
    const available=inventoryData.filter(i=>!inventoryTracksStock(i)||Number(i.stock||0)>0);
    const itemSelect=document.getElementById("newDrinkItem");
    itemSelect.innerHTML=available.map(i=>'<option value="'+i.id+'">'+i.category+' - '+i.name+'（'+inventoryStockText(i)+'）</option>').join("");
    document.getElementById("newDrinkQty").value="1";
    onNewDrinkItemChange();
    showModal("drinksModal");
  }catch(e){alert("加载消费明细失败: "+e);}
}

function onNewDrinkItemChange(){
  const itemId=parseInt(document.getElementById("newDrinkItem").value),item=inventoryData.find(i=>i.id===itemId);
  const unitSelect=document.getElementById("newDrinkSaleUnit");
  if(!item){unitSelect.innerHTML="";document.getElementById("newDrinkHint").textContent="暂无可售库存";return;}
  const unit=item.unit_name||inventoryUnitFor(item.category);
  let options='<option value="unit">'+unit+'（'+Number(item.unit_price||0).toFixed(2)+'元）</option>';
  if(item.category==="酒水"&&Number(item.case_size||0)>=2&&Number(item.case_price||0)>0){
    options+='<option value="case">箱（'+item.case_size+unit+'，'+Number(item.case_price||0).toFixed(2)+'元）</option>';
  }
  unitSelect.innerHTML=options;
  updateNewDrinkHint();
}
function updateNewDrinkHint(){
  const itemId=parseInt(document.getElementById("newDrinkItem").value),item=inventoryData.find(i=>i.id===itemId);
  if(!item)return;
  const saleUnit=document.getElementById("newDrinkSaleUnit").value,qty=Math.max(1,parseInt(document.getElementById("newDrinkQty").value)||1);
  const unitSize=saleUnit==="case"?Number(item.case_size||0):1;
  const price=saleUnit==="case"?Number(item.case_price||0):Number(item.unit_price||0);
  const required=qty*unitSize,unit=item.unit_name||inventoryUnitFor(item.category),tracks=inventoryTracksStock(item);
  const enough=!tracks||Number(item.stock||0)>=required;
  const hint=document.getElementById("newDrinkHint");
  hint.textContent=tracks?("库存："+inventoryStockText(item)+"；本次扣减 "+required+unit+"；金额 "+(qty*price).toFixed(2)+" 元"):("本次只记金额，不自动扣库存；金额 "+(qty*price).toFixed(2)+" 元");
  hint.style.color=enough?"var(--text-dim)":"var(--danger)";
}
function renderDrinksEditTable(drinks){
  const tb=document.querySelector("#drinksEditTable tbody");if(!drinks.length){tb.innerHTML='<tr><td colspan="7" style="color:var(--text-dim);padding:20px;">暂无明细</td></tr>';return;}
  tb.innerHTML=drinks.map(d=>{
    const label=drinkUnitLabel(d),subtotal=(Number(d.qty||0)*Number(d.unit_price||0)).toFixed(2),isPackage=d.source==="package";
    const operation=isPackage?'<span style="font-size:12px;color:var(--accent);">套餐包含</span>':'<button class="btn btn-xs btn-danger" onclick="deleteDrink('+d.id+')">删除</button>';
    const stockText=Number(d.stock_qty||0)>0?Number(d.stock_qty):"不联动";
    return '<tr><td>'+(isPackage?'[套餐] ':'')+escapeHtml(d.item_name)+'</td><td>'+label+(Number(d.unit_size||1)>1?'（'+d.unit_size+'基础单位）':'')+'</td><td>'+Number(d.unit_price||0).toFixed(2)+'</td><td>'+d.qty+'</td><td>'+subtotal+'</td><td>'+stockText+'</td><td>'+operation+'</td></tr>';
  }).join("");
}async function addDrinkFromModal(){
  if(!currentBilling)return;
  const inventoryId=parseInt(document.getElementById("newDrinkItem").value),qty=parseInt(document.getElementById("newDrinkQty").value)||1;
  if(!inventoryId){alert("暂无可售库存物品");return;}
  const body={billing_id:currentBilling.id,inventory_id:inventoryId,sale_unit:document.getElementById("newDrinkSaleUnit").value,qty};
  try{
    const r=await fetch(API.addDrink,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}),j=await r.json();
    if(r.ok&&j.code===0)showDrinksModal();else alert("添加失败: "+(j.detail||"unknown"));
  }catch(e){alert("请求失败: "+e);}
}

async function deleteDrink(drinkId){
  if(!confirm("确认删除该明细？已扣库存的商品会自动退回库存。"))return;
  const r=await fetch(API.drinkDelete+"/"+drinkId,{method:"DELETE"}),j=await r.json();
  if(r.ok&&j.code===0)showDrinksModal();else alert("删除失败: "+(j.detail||"unknown"));
}
function closeDrinksModal(){
  closeModal("drinksModal");
  if(currentBilling){
    fetch(API.billingActive).then(r=>r.json()).then(json=>{
      if(json.code!==0)return;
      const bill=json.data.find(b=>b.id===currentBilling.id);if(!bill)return;
      currentBilling=bill;
      document.getElementById("settleDrinksFee").textContent=Number(bill.drinks_fee||0).toFixed(2);
      renderSettleDrinkSummary(bill.drinks||[]);
      updateSettleTotal();
      fetchInventory();
    });
  }
}

function saveDrinksModal(){closeDrinksModal();}



