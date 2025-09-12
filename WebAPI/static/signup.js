(function () {
  // Shake on server-side error (flash with category 'error')
  var box = document.getElementById('signupBox');
  if (box && box.dataset.hadError === 'true') {
    box.classList.remove('shake');
    void box.offsetWidth; // restart animation
    box.classList.add('shake');
  }

  // Client-side password policy enforcement
  var pw = document.getElementById('password');
  var btn = document.getElementById('submitBtn');
  var ruleLength = document.getElementById('ruleLength');
  var ruleClasses = document.getElementById('ruleClasses');

  if (!pw || !btn || !ruleLength || !ruleClasses) return;

  function classify(p) {
    var lower = /[a-z]/.test(p);
    var upper = /[A-Z]/.test(p);
    var digit = /[0-9]/.test(p);
    var symbol = /[!@#$%^&*()_+\-=\[\]{};':",.<>\/?\\|]/.test(p);
    var classes = (lower?1:0) + (upper?1:0) + (digit?1:0) + (symbol?1:0);
    return { lengthOK: p.length >= 10, classesOK: classes >= 3 };
  }

  function update() {
    var v = pw.value || '';
    var res = classify(v);
    ruleLength.classList.toggle('ok', res.lengthOK);
    ruleClasses.classList.toggle('ok', res.classesOK);
    btn.disabled = !(res.lengthOK && res.classesOK);
  }

  pw.addEventListener('input', update);
  update();

  document.getElementById('signupForm').addEventListener('submit', function (e) {
    if (btn.disabled) {
      e.preventDefault();
      if (box) {
        box.classList.remove('shake');
        void box.offsetWidth;
        box.classList.add('shake');
      }
    }
  });
})();
