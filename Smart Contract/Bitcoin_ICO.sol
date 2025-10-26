//Bitcoin ICO

// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.0;

contract BitcoinICO{

    // Introducing the name of the token
    string public name = "Bitcoin";

    // Introducing total num Bitcoin that is 1 Million for sale
    uint public max_bitcoin = 1000000;

    // Introducing the price of each Bitcoin in USD (conversion rate)
    uint public price = 10;

    // Introducing the total number of Bitcoins that have bought by investors
    uint public total_bitcoin_bought = 0;

    // Mapping from the investor address to its equity 
    mapping(address => uint) public investor_equity_BTC;
    mapping(address => uint) public investor_equity_USD;
    
    // Check if an investor can buy BTC
    modifier can_buy_btc(uint usd_invested) {
        require (usd_invested * price + total_bitcoin_bought <= max_bitcoin);
        _;
    }

    // Checking the equity in BTC of an investor
    function equity_in_BTC(address investor) external view returns(uint){
        return investor_equity_BTC[investor];
    }


    // Checking the equity in USD of an investor
    function equity_in_USD(address investor) external view returns(uint){
        return investor_equity_USD[investor];
    }


}