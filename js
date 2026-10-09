/* Single job page: job/index.html?id=JOBID  (reads js/data.js, no server or API needed) */
(function () {
  var d = IH.load();
  IH.header('jobs', d);
  IH.footer(d);
  var box = document.getElementById('job');
  var id = window.JOB_ID || new URLSearchParams(location.search).get('id') || new URLSearchParams(location.search).get('job') || '';
  var j = d.jobs.filter(function (x) { return x.id === id; })[0];

  if (!j) {
    document.title = 'Job not found - TechnoJobs';
    box.innerHTML = '<div class="jobcard"><h1>This job is no longer listed</h1>' +
      '<p>It may have been filled or removed. You can see all the latest jobs on our website.</p>' +
      '<div class="actions"><a class="btn gold" href="' + IH.base + 'jobs/index.html">See all jobs <b class="arr">➜</b></a></div></div>';
    return;
  }

  var link = IH.safeUrl(j.link);
  var exp = j.level === 'Fresher' ? 'Fresher' : j.level === 'Both' ? 'Fresher / ' + (j.years || 'Experienced') : (j.years || 'Experienced');
  document.title = j.title + ' at ' + j.company + ' - TechnoJobs';

  box.innerHTML = '<div class="jobcard">' +
    '<div class="mhead">' + IH.logo(j) + '<div><h1>' + IH.esc(j.title) + '</h1><div style="color:var(--muted)">' + IH.esc(j.company) + '</div></div></div>' +
    '<div class="meta">' +
    '<div><small>Location</small>' + IH.esc(j.location) + '</div>' +
    '<div><small>Job type</small>' + IH.esc(j.type) + '</div>' +
    '<div><small>Experience</small>' + IH.esc(exp) + '</div>' +
    '<div><small>Qualification</small>' + IH.esc(j.qualification || 'Not specified') + '</div>' +
    '<div><small>Role</small>' + IH.esc(j.role || j.title) + '</div>' +
    '<div><small>Salary / stipend</small>' + IH.esc(j.pay || 'Not disclosed') + '</div></div>' +
    (j.details ? '<h4>About the job</h4><p>' + IH.esc(j.details) + '</p>' : '') +
    (j.requirements ? '<h4>Requirements</h4><p>' + IH.esc(j.requirements) + '</p>' : '') +
    (link ? '<div class="verified">✔ Direct link to the company\'s apply page</div>' : '') +
    '<div class="actions">' +
    (link ? '<a class="btn gold" id="apply" href="' + IH.esc(link) + '" target="_blank" rel="noopener noreferrer">Apply on company website <b class="arr">➜</b></a>' : '') +
    '<button class="btn ghost" id="share" type="button">Share this job</button>' +
    '<button class="btn ghost" id="copylink" type="button">Copy link</button>' +
    '<button class="btn ghost" id="copylink" type="button">Copy link</button>' +
    '<a class="btn ghost" href="' + IH.base + 'resume/index.html?job=' + encodeURIComponent(j.id) + '">Check my resume match</a>' +
    '</div></div>' +
    '<div class="backhome"><a href="' + IH.base + 'jobs/index.html">← See more jobs</a></div>';

  var ap = document.getElementById('apply');
  if (ap) ap.addEventListener('click', function () { IH.markApplied(j.id); });
  document.getElementById('share').addEventListener('click', function () { IH.share(j); });
  document.getElementById('copylink').addEventListener('click', function () {
    var u = IH.jobLink(j);
    var ok = function () { IH.toast('Link copied'); };
    if (navigator.clipboard) navigator.clipboard.writeText(u).then(ok, function () { IH.toast(u); }); else IH.toast(u);
  });
})();
