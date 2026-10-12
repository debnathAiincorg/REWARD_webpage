// Searchable employee combobox (templates/_employee_combo.html), shared by
// every section's Add Entry page. The visible box filters; the hidden #name
// input carries the chosen value, so the posted payload is identical to the
// plain <select> this replaced.
//
// After a pick (or when typing clears it) the hidden input fires "change",
// and the combo fires "employee:pick" with the chosen name, so a page can
// react — e.g. Employee Whatsapp splits it into First / Last name.
(() => {
  const combo = document.getElementById('nameCombo');
  if (!combo) return;
  const hidden = document.getElementById('name');
  const search = document.getElementById('nameSearch');
  const panel = document.getElementById('nameOptions');
  const list = document.getElementById('nameList');
  const emptyMsg = document.getElementById('comboEmpty');
  const newInput = document.getElementById('newEmployee');
  const nameError = document.getElementById('nameError');

  const options = () => Array.from(list.querySelectorAll('.combo-option'));
  const openPanel = () => { panel.hidden = false; search.setAttribute('aria-expanded', 'true'); };
  const closePanel = () => { panel.hidden = true; search.setAttribute('aria-expanded', 'false'); };
  const changed = () => hidden.dispatchEvent(new Event('change', { bubbles: true }));

  function applyFilter() {
    const q = search.value.trim().toLowerCase();
    let visible = 0;
    options().forEach(opt => {
      const match = opt.dataset.name.toLowerCase().includes(q);
      opt.hidden = !match;
      if (match) visible++;
    });
    emptyMsg.hidden = visible > 0;
  }

  function choose(name) {
    hidden.value = name;
    search.value = name;
    options().forEach(o => o.classList.toggle('selected', o.dataset.name === name));
    search.classList.remove('invalid');
    if (nameError) nameError.classList.remove('show');
    closePanel();
    changed();
    combo.dispatchEvent(new CustomEvent('employee:pick', { detail: { name: name } }));
  }

  search.addEventListener('focus', () => { openPanel(); applyFilter(); });

  search.addEventListener('input', () => {
    // Typing is a search, not a pick — drop the previous selection until they
    // actually choose, so a half-typed name can't be submitted as a real one.
    if (hidden.value) { hidden.value = ''; changed(); }
    openPanel();
    applyFilter();
  });

  search.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();  // never submit the entry form straight from the search box
      const first = options().find(o => !o.hidden);
      if (first) choose(first.dataset.name);
    } else if (e.key === 'Escape') {
      closePanel();
    }
  });

  list.addEventListener('click', (e) => {
    const pick = e.target.closest('.combo-pick');
    if (pick) {
      choose(pick.closest('.combo-option').dataset.name);
      return;
    }
    const remove = e.target.closest('.combo-remove');
    if (remove) {
      const name = remove.dataset.name;
      if (confirm(`Remove ${name} from list? Past entries won't be affected.`)) {
        document.getElementById('empDeleteName').value = name;
        document.getElementById('empDeleteForm').submit();
      }
    }
  });

  function submitNewEmployee() {
    const name = newInput.value.trim();
    if (!name) { newInput.focus(); return; }
    document.getElementById('empAddName').value = name;
    document.getElementById('empAddForm').submit();
  }

  document.getElementById('addEmployeeBtn').addEventListener('click', submitNewEmployee);
  newInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); submitNewEmployee(); }
  });

  document.addEventListener('click', (e) => {
    if (!combo.contains(e.target)) closePanel();
  });
})();
