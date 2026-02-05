// dashboard.js — Connects UI to Flask backend

let expenseBlob = null;
let goalBlob = null;

// 🎙 Expense Recording
const startRec = document.getElementById('startRec');
const stopRec = document.getElementById('stopRec');
const sendExpense = document.getElementById('sendExpense');
const audioPlayback = document.getElementById('audioPlayback');

let expenseRecorder;

startRec.onclick = async () => {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  expenseRecorder = new MediaRecorder(stream);
  const chunks = [];

  expenseRecorder.ondataavailable = e => chunks.push(e.data);
  expenseRecorder.onstop = () => {
    expenseBlob = new Blob(chunks, { type: 'audio/webm' });
    audioPlayback.src = URL.createObjectURL(expenseBlob);
    sendExpense.disabled = false;
  };

  expenseRecorder.start();
  startRec.disabled = true;
  stopRec.disabled = false;
};

stopRec.onclick = () => {
  expenseRecorder.stop();
  startRec.disabled = false;
  stopRec.disabled = true;
};

// 📤 Send Expense Audio to Backend
sendExpense.onclick = async () => {
  const formData = new FormData();
  formData.append('audio', expenseBlob, 'expense.webm');

  const response = await fetch('/upload-audio', { method: 'POST', body: formData });
  const data = await response.json();
  console.log('Expense Response:', data);
  sendExpense.disabled = true;
  loadExpenses(); // refresh list
};

// 🎯 Goal Recording
const startGoalRec = document.getElementById('startGoalRec');
const stopGoalRec = document.getElementById('stopGoalRec');
const sendGoal = document.getElementById('sendGoal');
const goalPlayback = document.getElementById('goalAudioPlayback');

let goalRecorder;

startGoalRec.onclick = async () => {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  goalRecorder = new MediaRecorder(stream);
  const chunks = [];

  goalRecorder.ondataavailable = e => chunks.push(e.data);
  goalRecorder.onstop = () => {
    goalBlob = new Blob(chunks, { type: 'audio/webm' });
    goalPlayback.src = URL.createObjectURL(goalBlob);
    sendGoal.disabled = false;
  };

  goalRecorder.start();
  startGoalRec.disabled = true;
  stopGoalRec.disabled = false;
};

stopGoalRec.onclick = () => {
  goalRecorder.stop();
  startGoalRec.disabled = false;
  stopGoalRec.disabled = true;
};

// 📤 Send Goal Audio
sendGoal.onclick = async () => {
  const formData = new FormData();
  formData.append('audio', goalBlob, 'goal.webm');

  const response = await fetch('/api/voice_goal', { method: 'POST', body: formData });
  const data = await response.json();
  console.log('Goal Response:', data);
  sendGoal.disabled = true;
  loadGoals(); // refresh goals
};

// 📋 Fetch and Display Expenses
async function loadExpenses() {
  const res = await fetch('/api/expenses');
  const expenses = await res.json();
  const ul = document.getElementById('expensesUl');
  ul.innerHTML = '';
  expenses.forEach(e => {
    const li = document.createElement('li');
    li.textContent = `${e.amount} ₹ - ${e.category} (${e.payment_method}) [${new Date(e.timestamp).toLocaleString()}]`;
    ul.appendChild(li);
  });
  drawCategoryChart(expenses);
}

// 🧾 Fetch and Display Goals
async function loadGoals() {
  const res = await fetch('/api/goals');
  const goals = await res.json();
  const ul = document.getElementById('goalsUl');
  ul.innerHTML = '';
  goals.forEach(g => {
    const li = document.createElement('li');
    const progress = (g.saved / g.target) * 100;
    li.innerHTML = `
      <strong>${g.name}</strong>: ₹${g.saved} / ₹${g.target}
      <div class="progress-bar">
        <div class="progress" style="width:${progress}%;"></div>
      </div>
    `;
    ul.appendChild(li);
  });
}

// 📊 Chart: Category-wise expenses
function drawCategoryChart(expenses) {
  const ctx = document.getElementById('categoryChart').getContext('2d');
  const totals = {};

  expenses.forEach(e => {
    totals[e.category] = (totals[e.category] || 0) + e.amount;
  });

  new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: Object.keys(totals),
      datasets: [{ data: Object.values(totals) }]
    }
  });
}

// 🚀 Initial Load
loadExpenses();
loadGoals();
