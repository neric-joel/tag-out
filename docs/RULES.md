# Rules and sources

All quotes below were fetched on 2026-10-24 and are verbatim from the linked pages (wrapped lines joined with a single space; spelling, punctuation and quote marks kept as the page has them).

## aca_25_avg

Source 1 (fetched 2026-10-24): https://public.powerdms.com/ASU/documents/1560576 (serves a PDF: Student Services Manual, SSM 305-05 "Limitations on Work Hours", Effective 1/8/1980, Revised 3/1/2024)

> To safeguard the academic success of every student, all student employees are limited to a rolling average of 25 hours per week for the year.
> This maximum applies to the combined total of all jobs, including hours associated with stipends paid for employment. The rolling average is monitored biweekly.
> A student can work more hours in the summer, provided the student does not exceed an average of 25 hours per week for the first 12 months of ASU employment or, in subsequent years of employment, from October to October.
> Students who average more than 25 hours per week for the year will be terminated from all ASU jobs. The student who was terminated for exceeding the 25-hour maximum will not be eligible for rehire at ASU in an undergraduate or graduate student position for 26 weeks.

Source 2 (fetched 2026-10-24): https://cfo.asu.edu/aca-faqs-undergraduate-graduate-student-workers

> All undergraduate student workers are limited to a rolling average of 25 hours per week for the year.
> This maximum applies to the combined total of all jobs, including hours associated with stipends paid for services.
> Student-workers hired Oct. 1, 2013, or later cannot average more than 25 hours per week beginning the first of the month following their date of employment and continuing for 12 months.
> After their initial measurement period following ASU employment, they will be measured during the standard Affordable Care Act measurement period of October through September each year.
> An average of 25 hours per week for the first 12 months of ASU employment or, in subsequent years of employment from October through September.
> Student workers who exceed the 25-hour average must work with their supervisors to reduce their hours or terminate one or more jobs. Terminating all jobs does not reduce the average under ACA.
> Students who average more than 25 hours per week by the 11th month of their measurement period will be terminated from all ASU student jobs for a minimum of 26 consecutive weeks or six months.
> Note: Hours under any work-study program, however, will be counted when determining the employment maximums under the new employment guidelines for all students.
> Students holding hourly student worker positions only — no assistantships or graduate Intern appointments — during the academic year may work a maximum of 25 hours per week.

Source 3 (fetched 2026-10-24): https://studentemployment.asu.edu/students/international-students/hourly-limits-and-work-rules

> You may not average more than 25 hours per week for the year. This includes all positions (hourly or stipend). This is an ASU policy not an immigration regulation.

Our note: Tag Out adds up every ASU job a student holds (hourly, stipend and work-study hours) and projects the average for the current measurement period; a trade that would push the projected average over 25 h/week is blocked. The window is the first 12 months of ASU employment (starting the first of the month after hire), then the standard ACA period. Discrepancy: SSM 305-05 says "from October to October", while the ACA FAQ says "October through September". We use Oct 1 to Sep 30 (the FAQ's ACA measurement period) and keep it configurable. Rehire wait: SSM says 26 weeks; the FAQ says "a minimum of 26 consecutive weeks or six months" and adds the 11th-month trigger, so Tag Out warns before month 11. Because the FAQ says terminating all jobs does not reduce the average, Tag Out never suggests quitting as a fix. The FAQ's "maximum of 25 hours per week" line sits in the graduate-assistantship answer and reads as a weekly cap for graduate hourly-only workers; we expose it as an optional setting, off by default.

## f1_weekly_20

Source 1 (fetched 2026-10-24): https://studentemployment.asu.edu/students/international-students/hourly-limits-and-work-rules

> F-1/J-1 students are allowed to work on-campus for a limited number of hours per week.
> You are not allowed to work more than 20 hours per week during the fall and spring semesters.
> The work week should be calculated starting Monday and ending Sunday.
> If you work for Aramark, whose work schedules differ from ASU, you must still calculate your weekly work hours from Monday to Sunday. It is important that you do not exceed this hourly limit.
> You cannot average hours worked over the ASU two-week pay period. You are only allowed to work up to 20 hours each week.
> For example, you cannot work 18 hours one week and then 22 hours the next.
> If you have more than one employer, you are only allowed to work for a total of 20 hours per week combined during the semester and 40 hours per week combined during the summer semester/winter or spring break.
> If you hold both a stipend position and an hourly position, you are responsible for tracking the hours you work for your stipend role. When combining those hours with the time worked in your hourly position, your total work hours must not exceed the established hourly limits.
> Exceeding the hourly limit will result in the loss of your F-1/J-1 immigration status, which requires departure from the U.S. and re-entry to gain a new immigration status.

Source 2 (fetched 2026-10-24): https://public.powerdms.com/ASU/documents/1560576 (SSM 305-05 PDF)

> International students with an F1 visa are allowed to work only 20 hours per week during the academic year and up to 40 hours per week during break periods in the winter and spring (provided the student does not exceed an average of 25 hours per week for the year).

Source 3 (fetched 2026-10-24): https://cfo.asu.edu/aca-faqs-undergraduate-graduate-student-workers

> International student workers with an F1 Visa are limited to 20 hours per week during the academic year and cannot exceed the rolling average of 25 hours per week for their 12-month measurement period.

Source 4 (fetched 2026-10-24): https://www.law.cornell.edu/cfr/text/8/214.2 (8 CFR 214.2(f)(9)(i), On-campus employment)

> Employment authorized under this paragraph (f)(9)(i) must not exceed 20 hours a week while school is in session, unless the Secretary suspends the applicability of this limitation due to emergent circumstances, as determined by the Secretary, by means of notice in the Federal Register, the student demonstrates to the DSO that the employment is necessary to avoid severe economic hardship resulting from the emergent circumstances, and the DSO notates the Form I-20 or successor form in accordance with the Federal Register document.
> An F-1 student may, however, work on campus full-time when school is not in session or during the annual vacation.

Our note: Tag Out treats a week as Monday 00:00 to Sunday 23:59 (Arizona time) and sums hours across every on-campus employer, including stipend hours, for students marked F-1 or J-1. During fall and spring a trade that would take that week over 20 h is a hard block, and hours are never averaged across the two-week pay period. Wording differences: the current federal text says "20 hours a week" (numerals, not "twenty") "while school is in session" and now carries an emergent-circumstances exception; the SSM and ACA FAQ only mention F1, while the Student Employment page covers F-1 and J-1. The Student Employment page says exceeding the limit "will result in the loss" of status; ISSC (see f1_break_40) says "may jeopardize". We show the stronger wording.

## f1_break_40

Source 1 (fetched 2026-10-24): https://studentemployment.asu.edu/students/international-students/hourly-limits-and-work-rules

> 40 hours per week (F-1 students may only work up to 20 hours per week if summer is their first or final semester)
> Note: F-1/J-1 students are limited to working on-campus 20 hours per week in summer in the following situations:
> Your I-20 has a program start date for summer.
> This includes students who finalized their degree program at the end of spring semester and will begin a new degree program in summer.
> Summer is the final semester of your degree program.
> Please see the Weekly Hourly Limit for On-Campus Employment for F-1/J-1 Students chart below for specific dates for when you can work 20 hours per week and 40 hours per week.

Cell text copied from that page's "Weekly Hourly Limit for On-Campus Employment for F-1/J-1 Students" chart (table cells, not a blockquote):

| Term | Up to 20 hours per week | Up to 40 hours per week | Last day of employment for students graduating in a specific semester |
|---|---|---|---|
| Winter Break 2025-2026 | | December 15, 2025 - January 11, 2026 | |
| Spring 2026 | January 12, 2026 - May 10, 2026 | March 9 - March 15, 2026 (Spring break) | May 11 2026 Or on student's designated program completion date |
| Summer 2026 | May 11 - August 16, 2026 if graduating in the summer. | May 11 - August 16, 2026 if continuing into fall 2026 | Session A: June 26, 2026 Session C: July 10, 2026 Session B: August 11, 2026 *Depends on student's last day of course enrollment. |
| Fall 2026 | August 17, 2026 - December 13, 2026 | | December 14, 2026 Or on student's designated program completion date |
| Winter Break 2026-2027 | | December 14, 2026 - January 10, 2027 | |
| Spring 2027 | January 11, 2027 - May 09, 2027 | March 8 - March 14, 2027 (Spring break) | May 10, 2027 Or on student's designated program completion date |
| Summer 2027 | May 17 - August 19, 2027 if graduating in the summer | May 17 - August 19, 2027 if continuing into fall 2027 | Session A: June 25, 2027 Session C: July 9, 2027 Session B: August 10, 2027 *Depends on student's last day of course enrollment. |
| Fall 2027 | August 19, 2027 - December 12, 2027 | | December 13, 2027 Or on student's designated program completion date |

Source 2 (fetched 2026-10-24): https://issc.asu.edu/news/work-hour-limits-f-1-students-during-semester-break (news post dated December 01, 2025)

> If you’re enrolled in or planning to enroll for spring 2026, you can work on campus up to 40 hours per week from December 15, 2025, to January 11, 2026.
> If fall 2025 is your last semester, however, you won’t be able to work on campus after your program completion date.
> Keep in mind that the 40-hour limit applies to each individual week, not as an average over ASU’s 2-week pay period.
> For example, you can’t work 38 hours one week and 42 the next; each week is limited to 40 hours.
> Working more than 40 hours per week during the semester break for on-campus employment may jeopardize your immigration status.

Source 3 (fetched 2026-10-24): https://public.powerdms.com/ASU/documents/1560576 (SSM 305-05 PDF), see the F1 sentence quoted under f1_weekly_20 ("up to 40 hours per week during break periods in the winter and spring").

Our note: Tag Out raises the F-1/J-1 weekly cap from 20 to 40 h only for Monday-to-Sunday weeks inside a 40-hour window from the chart above. On 2026-10-24 we are in Fall 2026 (20 h); the next 40-hour windows are Winter Break 2026-2027 (December 14, 2026 - January 10, 2027, Monday to Sunday) and spring break 2027 (March 8 - March 14, 2027). Summer is 40 h unless summer is the student's first or final semester, which stays at 20 h. Students graduating that term cannot pick up shifts after their last day of employment. Gaps in the chart: Spring 2027 ends May 09, 2027 but Summer 2027 starts May 17, 2027, so May 10-16, 2027 is not covered, and Summer 2027 ends August 19, 2027 (a Thursday), the same day Fall 2027 starts. Days the chart does not cover default to the safer 20 h. The ISSC post covers the 2025-2026 break only, so the 2026-2027 dates come from the Student Employment chart. All dates are data in config, not code.

## fws_award

Source 1 (fetched 2026-10-24): https://studentemployment.asu.edu/students/preparing-student-employment/federal-work-study

> You can only earn up to the amount of your FWS award. Once reached, your employer may continue your position under the Hourly Employment Program, though continuation is not guaranteed.
> You may earn only up to the amount of your FWS award.
> Your employer may choose to continue your position under the Hourly Employment Program, though this is not guaranteed and depends on department funding.
> Have an FWS award listed on your FAN via My ASU.
> FWS employment must end on your graduation day.
> FWS wages are paid biweekly for hours actually worked and are subject to federal taxes.

The page's "Work hours" cards are drawn by JavaScript; their text below was copied from the card data embedded in the same page:

> U.S. citizens and eligible noncitizens cannot work more than an average of 25 hours per week (62.5% FTE) across all university jobs, including stipends.
> Graduate assistants are limited to 20 hours per week total across all ASU positions.

Source 2 (fetched 2026-10-24, added because the FWS page does not mention international students): https://studentemployment.asu.edu/students/international-students/campus-employment-types

> Not eligible for federal work study positions

Our note: Tag Out tracks FWS earnings to date (hours x pay rate) against the award amount the student enters, and blocks an FWS-funded pickup that would go past the remaining award. After that, the shift only counts as allowed if the department has moved the position to the Hourly Employment Program. F-1/J-1 students are never offered FWS-funded shifts. The FWS page itself does not say "international students are not eligible"; that line comes from the international on-campus employment types page, where it is listed for F-1/J-1 students. The FWS calculator on the page divides by 20 hours/week; we use that only as a planning default, not as a rule.

## weekly_40

Source 1 (fetched 2026-10-24): https://public.powerdms.com/ASU/documents/1560576 (SSM 305-05 PDF)

> Students should not work more than a total of 40 hours per week.
> If a student works in excess of 40 hours in a work week (provided the student does not exceed an average of 25 hours per week for the year) then the overtime provisions of the Fair Labor Standards Act do apply and departments either have to pay 1.5 times the hourly rate or award 1.5 hours of compensatory time for each hour in excess of 40 hours worked in the work week.

Source 2 (fetched 2026-10-24): https://cfo.asu.edu/aca-faqs-undergraduate-graduate-student-workers

> Also, student positions are limited to part-time work, which is less than 40 hours or a full-time 40-hour workweek.
> Students holding hourly student worker positions may work up to a maximum of 40 hours per week during the summer.

Our note: Tag Out caps every student at 40 h per Monday-to-Sunday week across all jobs and blocks any trade that would go over it. The SSM says "should not" rather than "may not" and treats overtime as payable, so this is a policy cap the department pays for, not an immigration rule. The SSM does not define the work-week boundaries; we reuse Monday to Sunday from the international page. The cap is configurable.

## class_time

Source 1 (fetched 2026-10-24): https://public.powerdms.com/ASU/documents/1560576 (SSM 305-05 PDF)

> Federal Work-Study or hourly student employees may not work during the hours they are scheduled to be in class.

Source 2 (fetched 2026-10-24): https://studentemployment.asu.edu/students/preparing-student-employment/federal-work-study

> Meet standard student eligibility criteria, including being enrolled in at least one credit hour and not working during class times.
> FWS employees may not work during scheduled class times.

Source 3 (fetched 2026-10-24): https://studentemployment.asu.edu/students/international-students/campus-employment-types

> Employment must not interfere with full-time study. You cannot work during your class times.

Our note: Tag Out checks each shift against the class schedule the student enters and blocks any overlap. This applies to every student (SSM covers FWS and hourly employees; the international page says the same for F-1/J-1). Travel time between campuses is advice from the scheduling page, not a rule; Tag Out offers an optional buffer.

## coverage_on_student

Source (fetched 2026-10-24): https://studentemployment.asu.edu/students/starting-your-role/developing-schedule

> Be proactive about finding shift coverage (if applicable).
> Understand the process for requesting time off or changing shifts (including how far in advance schedules are set)
> Confirm your schedule in writing (email or shared calendar)
> Talk with your supervisor early about adjustments. Avoid shifting your regular schedule too often, but be honest with your supervisor if you need adjustments on a certain day due to exams, extracurricular events, etc.
> Remember: Your education comes first, but being dependable and communicative helps build trust with your employer.
> Clarify expected hours: Ask how many hours per week are expected or allowed. (Most ASU student employees can work up to 20 hours/week during semesters.)

Our note: ASU guidance puts finding coverage on the student. Tag Out makes that safe: the student posts a shift, coworkers claim it, every rule above is checked for the person picking it up, and the supervisor approves. The page's "(Most ASU student employees can work up to 20 hours/week during semesters.)" is general advice and does not match the 25-hour average policy; Tag Out does not enforce 20 h for domestic students unless a department sets it.

## stats

Source (fetched 2026-10-24): https://workplus.asu.edu/impact (redirected to https://workplus.asu.edu/learn-more/impact)

> Approximately 10,000 students work at ASU each year, creating an opportunity to build transferable skills and career readiness at scale.
> 7 out of 10
> Undergraduate students work at least one job at some point during their time at ASU.
> They work 11-20 hours per week, and nearly a quarter hold an additional off-campus job.
> At ASU, 50% of working learners have high or very high financial need, and many students face additional barriers to accessing traditional career-building experiences.
> Source: ASU Annual Student Employment Survey (24-25)

Our note: Used in the pitch only, not enforced. "7 out of 10" is a large-number display directly above the "Undergraduate students work at least one job..." line. The 11-20 hours line sits under the heading "Most college students are stretched thin", and the survey source line comes after the 50% paragraph, so we cite both to the ASU Annual Student Employment Survey (24-25) as the page does.

Not legal or immigration advice. Your DSO and ASU Student Employment decide. Rules are cited; limits are configurable.
