// FlyVR
// http://flyvisionlab.weebly.com/
// Contact: Steven Herbst <sherbst@stanford.edu>

#include "Utility.h"

double getColor(std::string s, ColorType t){

	if (s.find("x") == std::string::npos){
		return std::stod(s);
	}
	else{
		unsigned long lval = std::stoul(s, nullptr, 16); // parse hex string

		// Read out the desired byte
		if (t == ColorType::Red){
			lval = (lval >> 16) & 0xFF; // get red byte
		}
		else if (t == ColorType::Green){
			lval = (lval >> 8) & 0xFF; // get green byte
		}
		else if (t == ColorType::Blue){
			lval = (lval >> 0) & 0xFF; // get blue byte
		}
		
		// rescale to 0-to-1 range
		return (lval / 255.0); 
	}
}

void DelaySeconds(double t){
	auto stopTime = std::chrono::high_resolution_clock::now() + std::chrono::duration<double>(t);
	std::this_thread::sleep_until(stopTime);
}

double GetTimeStamp(){
	return std::chrono::duration<double>(std::chrono::high_resolution_clock::now().time_since_epoch()).count();
}