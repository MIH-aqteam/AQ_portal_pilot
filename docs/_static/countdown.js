document.addEventListener("DOMContentLoaded", function () {
    const countdownElement = document.getElementById("countdown");
    const trafficLight = document.getElementById("traffic-light");

    if (!countdownElement || !trafficLight) {
    return;
    }  

    const deadline = new Date("2026-09-30T23:59:59");

    function updateCountdown() {
        const now = new Date();
        const remaining = deadline - now;

    if (remaining <= 0) {
        countdownElement.textContent = "Reporting deadline has passed.";

        trafficLight.classList.remove(
            "traffic-green",
            "traffic-orange",
            "traffic-red"
    );

    trafficLight.classList.add("traffic-red");
    trafficLight.classList.add("traffic-all-red");

    return;
}
        const days = Math.floor(remaining / (1000 * 60 * 60 * 24));
        const hours = Math.floor(
            (remaining % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60)
        );

        countdownElement.textContent =
            days + " days and " + hours + " hours";

        trafficLight.classList.remove(
            "traffic-green",
            "traffic-orange",
            "traffic-red"
        );

        if (days >= 60) {
            trafficLight.classList.add("traffic-green");
        } else if (days >= 30) {
            trafficLight.classList.add("traffic-orange");
        } else {
            trafficLight.classList.add("traffic-red");
        }
    }

    updateCountdown();
    setInterval(updateCountdown, 60000);
});